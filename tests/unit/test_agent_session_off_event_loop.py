"""An agent's session waits for the database off the event loop.

Every message of a session (progress, log lines, heartbeats) committed on the
loop, and so did the token check and the hello at connect. A write lock held
elsewhere, or a pool with no free connection, then held every request of the
process until it was free.

The waits are laid out with a `Gate` that stops a session's database work, or
with the write lock or every pooled connection held by the test. With the work
back on the loop, `/health` cannot answer while it waits, the gate or the held
lock runs out, and the test fails after HOLD_SECONDS instead of hanging. No
test depends on how long anything takes.

The tests run on SQLite and, with BORG_TEST_POSTGRES_URL set, on PostgreSQL.
"""

import asyncio
import contextlib
import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool
from starlette.websockets import WebSocketDisconnect

import app.api.agents as agents
from app.database.database import Base, get_db, register_utc_session_timezone
from app.database.models import AgentJob, AgentJobLog, AgentMachine, Operation
from app.services.agent_connection_manager import agent_connection_manager
from tests.utils.operations import seed_job_operation

POSTGRES_URL = os.getenv("BORG_TEST_POSTGRES_URL")
RAW_TOKEN = "borgui_agent_" + "w" * 43
AGENT_ID = "agt_session"
# Long enough for a message to arrive, short enough that a wait held on the
# loop fails the test instead of hanging it.
HOLD_SECONDS = 5
# Connections in the app's pool: a session takes one at a time, the test's
# own sessions take one each.
POOL_SIZE = 2


class Gate:
    """Stops the first thread that reaches it until the test opens it."""

    def __init__(self) -> None:
        self.reached = threading.Event()
        self.opened_in_time: list[bool] = []
        self.reached_on_the_loop: list[bool] = []
        self._opened = threading.Event()
        self._lock = threading.Lock()
        self._taken = False

    def hold(self) -> None:
        with self._lock:
            if self._taken:
                return
            self._taken = True
        self.reached_on_the_loop.append(_on_the_loop())
        self.reached.set()
        self.opened_in_time.append(self._opened.wait(HOLD_SECONDS))

    def open(self) -> None:
        self._opened.set()


def _on_the_loop() -> bool:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return False
    return True


def _sqlite_engine(url):
    engine = create_engine(
        url,
        connect_args={"check_same_thread": False},
        poolclass=QueuePool,
        pool_size=POOL_SIZE,
        max_overflow=0,
        pool_timeout=HOLD_SECONDS * 2,
    )

    @event.listens_for(engine, "connect")
    def pragmas(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


@contextmanager
def _postgres_engine():
    """A schema of its own: the other PostgreSQL tests drop `public`."""
    schema = f"agent_session_{uuid.uuid4().hex}"
    admin = create_engine(POSTGRES_URL)
    with admin.begin() as conn:
        conn.execute(text(f"CREATE SCHEMA {schema}"))
    engine = create_engine(
        POSTGRES_URL,
        connect_args={"options": f"-c search_path={schema}"},
        poolclass=QueuePool,
        pool_size=POOL_SIZE,
        max_overflow=0,
        pool_timeout=HOLD_SECONDS * 2,
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


@contextmanager
def _engine_for(kind, test_db):
    if kind == "postgresql":
        with _postgres_engine() as engine:
            yield engine
        return
    engine = _sqlite_engine(test_db.get_bind().url)
    try:
        yield engine
    finally:
        engine.dispose()


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
def database(request, test_client, test_db):
    """Sessions on a pool of POOL_SIZE connections, one per session for the
    app, as in production, and for the test's setup and assertions."""
    from app.main import app

    with _engine_for(request.param, test_db) as engine:
        sessions = sessionmaker(autocommit=False, autoflush=False, bind=engine)

        def override_get_db():
            db = sessions()
            try:
                yield db
            finally:
                db.close()

        # Only the app's sessions: what else of the app runs meanwhile (the
        # operations runner) stays on the test's own database session.
        app.dependency_overrides[get_db] = override_get_db
        yield sessions


@pytest.fixture(autouse=True)
def agent_tokens_pass(monkeypatch):
    monkeypatch.setattr(
        "app.core.agent_auth.verify_password", lambda token, token_hash: True
    )


@pytest.fixture(autouse=True)
def no_leftover_logs():
    agent_connection_manager._logs.clear()
    yield
    agent_connection_manager._logs.clear()


def _seed_agent(sessions, **columns) -> int:
    with sessions() as db:
        agent = AgentMachine(
            name="Session Agent",
            agent_id=AGENT_ID,
            token_hash="checked by the test's stand-in",
            token_prefix=RAW_TOKEN[:20],
            status=columns.pop("status", "online"),
            capabilities=["session.commands", "backup.create"],
            **columns,
        )
        db.add(agent)
        db.commit()
        return agent.id


def _seed_job(sessions, agent_id: int, *, status: str = "running", **columns) -> int:
    now = datetime.now(timezone.utc)
    with sessions() as db:
        job = AgentJob(
            agent_machine_id=agent_id,
            job_type="repository",
            status=status,
            payload={"job_kind": "repository.delete_archive"},
            claimed_at=columns.pop("claimed_at", now),
            started_at=columns.pop("started_at", now if status == "running" else None),
            **columns,
        )
        db.add(job)
        db.commit()
        return job.id


def _seed_backup_job(sessions, agent_id: int) -> tuple[int, int]:
    """A backup handed to the agent whose start is not reported yet. Returns
    the operation's id and the agent job's."""
    now = datetime.now(timezone.utc)
    with sessions() as db:
        operation = seed_job_operation(
            db, "backup", repository="/session", status="running", started_at=now
        )
        db.commit()
        job = AgentJob(
            agent_machine_id=agent_id,
            job_type="backup",
            status="claimed",
            payload={
                "schema_version": 1,
                "job_kind": "backup.create",
                "repository": {"id": operation.repository_id},
            },
            operation_id=operation.id,
            claimed_at=now,
        )
        db.add(job)
        db.commit()
        return operation.id, job.id


def _set_columns(sessions, model, row_id: int, values: dict) -> None:
    """Commit a change the way another request would."""
    with sessions() as db:
        db.query(model).filter(model.id == row_id).update(
            values, synchronize_session=False
        )
        db.commit()


def _row(sessions, model, row_id: int):
    with sessions() as db:
        row = db.get(model, row_id)
        db.expunge(row)
        return row


def _hello(**overrides) -> dict:
    return {
        "type": "hello",
        "agent_id": AGENT_ID,
        "hostname": "session.local",
        "agent_version": "0.2.0",
        "borg_versions": [],
        "capabilities": ["session.commands", "backup.create"],
        "running_job_ids": [],
        **overrides,
    }


# Released each time a session's start is done (see `session_starts`).
_STARTED = threading.Semaphore(0)


@pytest.fixture(autouse=True)
def session_starts(monkeypatch):
    """The start sends what is queued after the ack, from a read in a thread:
    `_connected` waits for it, so a job a test queues afterwards is the
    test's."""
    while _STARTED.acquire(blocking=False):
        pass
    original = agents._send_queued_agent_jobs

    async def send_and_tell(db, jobs, *, source):
        try:
            await original(db, jobs, source=source)
        finally:
            if source == "session_reconnect":
                _STARTED.release()

    monkeypatch.setattr(agents, "_send_queued_agent_jobs", send_and_tell)


@contextmanager
def _connected(client, *, hello=None, running=()):
    """A session whose hello lists `running` (a job it leaves out would be
    queued again and sent at once), once its start is done."""
    with client.websocket_connect(
        "/api/agents/session",
        headers={"X-Borg-Agent-Authorization": f"Bearer {RAW_TOKEN}"},
    ) as websocket:
        websocket.send_json(hello or _hello(running_job_ids=list(running)))
        assert _receive(websocket)["type"] == "hello_ack"
        assert _STARTED.acquire(timeout=HOLD_SECONDS), "the session never started"
        yield websocket


class Handled:
    """The messages the session has handled (or refused), in order."""

    def __init__(self) -> None:
        self.messages: list[dict] = []
        self._changed = threading.Condition()

    def add(self, message: dict) -> None:
        with self._changed:
            self.messages.append(message)
            self._changed.notify_all()

    def is_set(self) -> bool:
        return bool(self.messages)

    def wait_for(self, message: dict, after: int) -> bool:
        """Whether `message` is handled, as one of those after the first
        `after`, within the wait."""
        with self._changed:
            return self._changed.wait_for(
                lambda: message in self.messages[after:], HOLD_SECONDS * 2
            )


@pytest.fixture
def handled(monkeypatch):
    done = Handled()
    original = agents._handle_agent_session_message

    async def handle_and_tell(db, agent_machine_id, message, **kwargs):
        try:
            await original(db, agent_machine_id, message, **kwargs)
        finally:
            done.add(message)

    monkeypatch.setattr(agents, "_handle_agent_session_message", handle_and_tell)
    return done


def _hold_in(monkeypatch, name: str, gate: Gate) -> None:
    """Stop `agents.<name>` at the gate before it runs."""
    original = getattr(agents, name)

    def held(*args, **kwargs):
        gate.hold()
        return original(*args, **kwargs)

    monkeypatch.setattr(agents, name, held)


def _while_held(gate: Gate, action, meanwhile):
    """Run `action` in a thread and `meanwhile` while the gate holds it."""
    with ThreadPoolExecutor(max_workers=1) as pool:
        held = pool.submit(action)
        assert gate.reached.wait(HOLD_SECONDS), "the session never reached the gate"
        other = meanwhile()
        gate.open()
        result = held.result(HOLD_SECONDS * 2)
    assert gate.opened_in_time == [True]
    assert gate.reached_on_the_loop == [False]
    return result, other


def _live_log(agent_id: int, job_id: int) -> list[str]:
    return [
        entry["message"]
        for entry in agent_connection_manager.list_logs(agent_id)
        if entry.get("job_id") == job_id
    ]


def _send_and_wait(websocket, handled, message) -> None:
    before = len(handled.messages)
    websocket.send_json(message)
    assert handled.wait_for(message, before), "the session never handled it"


def _receive(websocket) -> dict:
    """The next frame, or a failure instead of a test that hangs."""
    pool = ThreadPoolExecutor(max_workers=1)
    frame = pool.submit(websocket.receive_json)
    try:
        return frame.result(HOLD_SECONDS * 2)
    except TimeoutError:
        # The blocked receive ends once the test leaves the session.
        raise AssertionError("no frame came") from None
    finally:
        pool.shutdown(wait=False)


MESSAGES = {
    "progress": {"type": "progress", "progress_percent": 42.0, "nfiles": 3},
    "log": {"type": "log", "message": "a line", "sequence": 1},
    "heartbeat": {"type": "heartbeat", "running_job_ids": []},
    "command_ack": {"type": "command_ack"},
    "job_canceled": {"type": "job_canceled"},
    "command_error": {"type": "command_error", "error": {"message": "boom"}},
    "command_result": {"type": "command_result", "result": {"return_code": 0}},
}


# --- the loop answers while a session waits for the database ---------------


@pytest.mark.unit
@pytest.mark.parametrize("kind", MESSAGES)
def test_the_loop_answers_while_a_session_message_waits(
    test_client, database, handled, monkeypatch, kind
):
    agent_id = _seed_agent(database)
    job_id = _seed_job(database, agent_id)
    gate = Gate()

    with _connected(test_client, running=[job_id]) as websocket:
        # The first thing every message does: see that the agent is active.
        _hold_in(monkeypatch, "agent_is_active", gate)
        _, health = _while_held(
            gate,
            lambda: _send_and_wait(
                websocket, handled, {**MESSAGES[kind], "job_id": job_id}
            ),
            lambda: test_client.get("/health"),
        )

    assert health.status_code == 200


@pytest.mark.unit
def test_the_loop_answers_while_an_agent_connects(test_client, database, monkeypatch):
    _seed_agent(database)
    gate = Gate()

    def held_check(token, token_hash):
        gate.hold()
        return True

    monkeypatch.setattr("app.core.agent_auth.verify_password", held_check)

    def connect():
        with _connected(test_client):
            pass

    _, health = _while_held(gate, connect, lambda: test_client.get("/health"))

    assert health.status_code == 200


@pytest.mark.unit
def test_the_loop_answers_while_a_hello_waits(test_client, database, monkeypatch):
    _seed_agent(database)
    gate = Gate()
    _hold_in(monkeypatch, "_requeue_stale_agent_jobs", gate)

    def connect():
        with _connected(test_client):
            pass

    _, health = _while_held(gate, connect, lambda: test_client.get("/health"))

    assert health.status_code == 200


@pytest.mark.unit
def test_the_loop_answers_while_a_session_waits_for_a_connection(
    test_client, database, handled, monkeypatch
):
    """Every connection of the pool is held: the session's next message waits
    for one in its thread."""
    agent_id = _seed_agent(database)
    job_id = _seed_job(database, agent_id)
    asking = threading.Event()
    original = agents.agent_is_active

    def asking_for_a_connection(db, agent_machine_id):
        asking.set()
        return original(db, agent_machine_id)

    with _connected(test_client, running=[job_id]) as websocket:
        monkeypatch.setattr(agents, "agent_is_active", asking_for_a_connection)
        engine = database.kw["bind"]
        held = [engine.connect() for _ in range(POOL_SIZE)]
        released_in_time = []
        try:
            message = {**MESSAGES["progress"], "job_id": job_id}
            websocket.send_json(message)
            assert asking.wait(HOLD_SECONDS)
            health = test_client.get("/health")
            # Still held when /health came back: it did not need a connection.
            released_in_time.append(not handled.is_set())
        finally:
            for connection in held:
                connection.close()
        assert handled.wait_for(message, 0)

    assert health.status_code == 200
    assert released_in_time == [True]
    assert _row(database, AgentJob, job_id).nfiles == 3


@pytest.mark.unit
def test_the_loop_answers_while_sqlite_holds_its_write_lock(
    test_client, test_db, handled, monkeypatch
):
    """SQLite takes one writer at a time: a progress report waits for another
    connection's write to end."""
    engine = _sqlite_engine(test_db.get_bind().url)
    sessions = sessionmaker(bind=engine)
    from app.main import app

    def override_get_db():
        db = sessions()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    agent_id = _seed_agent(sessions)
    job_id = _seed_job(sessions, agent_id)
    writing = threading.Event()

    def on_write(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("UPDATE agent_jobs"):
            writing.set()

    try:
        with _connected(test_client, running=[job_id]) as websocket:
            event.listen(engine, "before_cursor_execute", on_write)
            try:
                writer = engine.connect()
                writer.exec_driver_sql("BEGIN IMMEDIATE")
                try:
                    message = {**MESSAGES["progress"], "job_id": job_id}
                    websocket.send_json(message)
                    assert writing.wait(HOLD_SECONDS)
                    health = test_client.get("/health")
                    lock_still_held = not handled.is_set()
                finally:
                    writer.exec_driver_sql("ROLLBACK")
                    writer.close()
                assert handled.wait_for(message, 0)
            finally:
                event.remove(engine, "before_cursor_execute", on_write)
    finally:
        engine.dispose()

    assert health.status_code == 200
    assert lock_still_held
    assert _row(sessions, AgentJob, job_id).nfiles == 3


# --- nothing of a session queries on the loop ------------------------------


@pytest.mark.unit
def test_no_statement_of_a_session_runs_on_the_loop(
    test_client, database, handled, monkeypatch
):
    """From the token check to the offline mark, every message kind; with a
    cancel owed and a running job listed, so the heartbeat's requeue and its
    reads take part."""
    agent_id = _seed_agent(database, status="offline")
    running_id = _seed_job(database, agent_id)
    cancel_id = _seed_job(database, agent_id, status="cancel_requested")
    _operation_id, backup_job_id = _seed_backup_job(database, agent_id)
    on_the_loop: list[str] = []
    off_the_loop: list[str] = []

    def record(conn, cursor, statement, parameters, context, executemany):
        (on_the_loop if _on_the_loop() else off_the_loop).append(statement)

    engine = database.kw["bind"]
    event.listen(engine, "before_cursor_execute", record)
    try:
        with _connected(
            test_client,
            hello=_hello(running_job_ids=[running_id, cancel_id, backup_job_id]),
        ) as websocket:
            assert _receive(websocket)["command"] == "cancel"
            _send_and_wait(
                websocket,
                handled,
                {"type": "job_started", "job_id": backup_job_id},
            )
            for kind, message in MESSAGES.items():
                if kind == "heartbeat":
                    message = {
                        **message,
                        "running_job_ids": [running_id, cancel_id, backup_job_id],
                    }
                _send_and_wait(websocket, handled, {**message, "job_id": running_id})
            websocket.send_json(["not", "a", "message"])
            _send_and_wait(websocket, handled, {"type": "unknown"})
    finally:
        event.remove(engine, "before_cursor_execute", record)

    assert any("agent_machines.token_prefix" in s for s in off_the_loop)
    assert any(s.startswith("UPDATE agent_jobs") for s in off_the_loop)
    assert on_the_loop == []
    assert _row(database, AgentMachine, agent_id).status == "offline"


@pytest.mark.unit
@pytest.mark.parametrize(
    ("kind", "verdict"), [("command_result", "completed"), ("command_error", "failed")]
)
def test_a_terminal_outcome_over_the_session_is_recorded_off_the_loop(
    test_client, database, handled, monkeypatch, kind, verdict
):
    """Recording the outcome finishes the linked job and can write its
    operation's log file (#1324 moved the REST report's off the loop)."""
    agent_id = _seed_agent(database)
    job_id = _seed_job(database, agent_id)
    recorded_on_the_loop = []
    name = "_complete_agent_job" if kind == "command_result" else "_fail_agent_job"
    original = getattr(agents, name)

    def recording(*args, **kwargs):
        recorded_on_the_loop.append(_on_the_loop())
        return original(*args, **kwargs)

    monkeypatch.setattr(agents, name, recording)
    with _connected(test_client, running=[job_id]) as websocket:
        _send_and_wait(websocket, handled, {**MESSAGES[kind], "job_id": job_id})

    assert recorded_on_the_loop == [False]
    assert _row(database, AgentJob, job_id).status == verdict


@pytest.mark.unit
@pytest.mark.parametrize("kind", [*MESSAGES, "job_started", "unknown"])
def test_a_session_holds_no_connection_between_messages(
    test_client, database, handled, kind
):
    agent_id = _seed_agent(database)
    if kind == "job_started":
        # A backup's first start report sends a notification, which reads.
        _operation_id, job_id = _seed_backup_job(database, agent_id)
    else:
        job_id = _seed_job(database, agent_id, status="claimed", started_at=None)
    engine = database.kw["bind"]

    # Listed, so the hello leaves the job to the agent and nothing is sent.
    with _connected(test_client, hello=_hello(running_job_ids=[job_id])) as websocket:
        # The session reads its first message once its start's reads are done.
        _send_and_wait(websocket, handled, {"type": "unknown"})
        assert engine.pool.checkedout() == 0
        _send_and_wait(
            websocket,
            handled,
            {**MESSAGES.get(kind, {"type": kind}), "job_id": job_id},
        )
        assert engine.pool.checkedout() == 0


# --- what stays as it was on the loop --------------------------------------


@pytest.mark.unit
def test_a_session_handles_its_messages_in_order(
    test_client, database, handled, monkeypatch
):
    """The session waits for a message's thread before it reads the next: a
    later report never lands before an earlier one."""
    agent_id = _seed_agent(database)
    job_id = _seed_job(database, agent_id)
    gate = Gate()
    applied: list[float] = []
    original = agents._apply_agent_job_progress

    def held_progress(job, db, progress):
        gate.hold()
        applied.append(progress["progress_percent"])
        return original(job, db, progress)

    with _connected(test_client, running=[job_id]) as websocket:
        monkeypatch.setattr(agents, "_apply_agent_job_progress", held_progress)
        sent = [
            {"type": "progress", "job_id": job_id, "progress_percent": 1.0},
            {"type": "progress", "job_id": job_id, "progress_percent": 2.0},
            {"type": "log", "job_id": job_id, "message": "x", "sequence": 1},
        ]
        websocket.send_json(sent[0])
        assert gate.reached.wait(HOLD_SECONDS)
        websocket.send_json(sent[1])
        websocket.send_json(sent[2])
        # The later messages wait for the first: /health answers meanwhile.
        assert test_client.get("/health").status_code == 200
        assert applied == []
        assert handled.messages == []
        gate.open()
        _send_and_wait(websocket, handled, {"type": "heartbeat"})

    assert gate.opened_in_time == [True]
    assert applied == [1.0, 2.0]
    assert handled.messages == [*sent, {"type": "heartbeat"}]
    assert _row(database, AgentJob, job_id).progress_percent == 2.0


@pytest.mark.unit
@pytest.mark.parametrize("kind", ["progress", "log", "heartbeat", "not a dict"])
def test_a_message_of_a_revoked_agent_is_refused(test_client, database, handled, kind):
    agent_id = _seed_agent(database)
    job_id = _seed_job(database, agent_id)

    with pytest.raises(WebSocketDisconnect) as closed:
        with _connected(test_client, running=[job_id]) as websocket:
            _set_columns(database, AgentMachine, agent_id, {"status": "revoked"})
            message = (
                ["not", "a", "dict"]
                if kind == "not a dict"
                else {**MESSAGES[kind], "job_id": job_id}
            )
            websocket.send_json(message)
            # Refused, the next message is never read.
            websocket.send_json({"type": "unknown"})
            _receive(websocket)

    assert closed.value.code == 1008
    if kind == "not a dict":
        assert not handled.is_set()
    job = _row(database, AgentJob, job_id)
    assert job.nfiles != MESSAGES["progress"]["nfiles"]
    with database() as db:
        assert db.query(AgentJobLog).count() == 0
    assert _live_log(agent_id, job_id) == []
    assert _row(database, AgentMachine, agent_id).status == "revoked"


@pytest.mark.unit
def test_a_hello_refuses_an_agent_revoked_after_its_token_check(
    test_client, database, monkeypatch
):
    agent_id = _seed_agent(database)
    original = agents._authenticate_session

    def revoked_meanwhile(token, db):
        result = original(token, db)
        _set_columns(database, AgentMachine, agent_id, {"status": "revoked"})
        return result

    monkeypatch.setattr(agents, "_authenticate_session", revoked_meanwhile)

    with pytest.raises(WebSocketDisconnect) as closed:
        with _connected(test_client):
            pass

    assert closed.value.code == 1008
    assert _row(database, AgentMachine, agent_id).status == "revoked"
    assert not agent_connection_manager.is_connected(agent_id)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_a_cancelled_message_waits_for_its_thread(test_db, monkeypatch):
    """A session cancelled mid-message (the server shuts down) goes on to
    close its database session only once the thread working on it is done."""
    agent = AgentMachine(
        name="Cancelled",
        agent_id="agt_cancelled",
        token_hash="unused",
        token_prefix="unused",
        status="online",
    )
    test_db.add(agent)
    test_db.commit()
    agent_id = agent.id
    job = AgentJob(
        agent_machine_id=agent_id,
        job_type="repository",
        status="running",
        payload={"job_kind": "repository.delete_archive"},
        claimed_at=datetime.now(timezone.utc),
        started_at=datetime.now(timezone.utc),
    )
    test_db.add(job)
    test_db.commit()
    job_id = job.id
    gate = Gate()
    _hold_in(monkeypatch, "_apply_agent_job_progress", gate)

    task = asyncio.ensure_future(
        agents._handle_agent_session_message(
            test_db,
            agent_id,
            {"type": "progress", "job_id": job_id, "nfiles": 5},
            check_active=True,
        )
    )
    assert await asyncio.to_thread(gate.reached.wait, HOLD_SECONDS)
    task.cancel()
    for _ in range(20):
        await asyncio.sleep(0)
    finished_before_its_thread = task.done()
    gate.open()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert finished_before_its_thread is False
    assert gate.opened_in_time == [True]
    test_db.expire_all()
    assert test_db.get(AgentJob, job_id).nfiles == 5


# --- which session speaks for the agent -------------------------------------


class _SignalledLocks:
    """Counts the coroutines that reached the session lock of an agent."""

    def __init__(self, monkeypatch):
        self.arrivals = threading.Semaphore(0)
        original = agents._agent_session_lock
        signalled = self

        class Signalled:
            def __init__(self, lock):
                self._lock = lock

            async def __aenter__(self):
                signalled.arrivals.release()
                return await self._lock.__aenter__()

            async def __aexit__(self, *exc):
                return await self._lock.__aexit__(*exc)

        monkeypatch.setattr(
            agents,
            "_agent_session_lock",
            lambda agent_machine_id: Signalled(original(agent_machine_id)),
        )

    def wait(self, count: int) -> None:
        for _ in range(count):
            assert self.arrivals.acquire(timeout=HOLD_SECONDS)


def _session_until(client, release: threading.Event, hello: dict) -> None:
    with _connected(client, hello=hello):
        assert release.wait(HOLD_SECONDS * 2)


@pytest.mark.unit
def test_two_hellos_at_once_count_one_list_as_complete(
    test_client, database, monkeypatch
):
    """A hello lists every job its process runs only while no other process
    holds a session for the agent. Two processes connecting at once (a
    rollout meeting a server restart) were decided one after the other on the
    loop; the second must still see the first."""
    _seed_agent(database)
    locks = _SignalledLocks(monkeypatch)
    gate = Gate()
    completeness: list[bool] = []
    original = agents._record_session_hello

    def recording(db, current_agent, hello, running_job_ids_complete):
        completeness.append(running_job_ids_complete)
        gate.hold()
        return original(db, current_agent, hello, running_job_ids_complete)

    monkeypatch.setattr(agents, "_record_session_hello", recording)
    hello = _hello(agent_version="0.1.21")
    release = threading.Event()

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(_session_until, test_client, release, hello)
        assert gate.reached.wait(HOLD_SECONDS)
        locks.wait(1)
        second = pool.submit(_session_until, test_client, release, hello)
        # The second hello is at the lock while the first is recorded.
        locks.wait(1)
        gate.open()
        release.set()
        first.result(HOLD_SECONDS * 2)
        second.result(HOLD_SECONDS * 2)

    assert gate.opened_in_time == [True]
    assert gate.reached_on_the_loop == [False]
    assert completeness == [True, False]


@pytest.mark.unit
@pytest.mark.parametrize(
    "step",
    [
        "_record_session_hello",
        "_requeue_stale_agent_jobs",
        "_record_session_message",
        "_mark_session_agent_offline",
    ],
)
def test_a_session_acts_for_the_agent_under_its_lock(
    test_client, database, handled, monkeypatch, step
):
    """Which session speaks for the agent is read on the loop, and the hello's
    requeue, the heartbeat's requeue and the disconnect's offline mark act on
    it in a thread. The agent's session lock keeps the two one step, as they
    were on the loop: a newer session's hello cannot land in between (its
    `online` before an older session's `offline`, or a second process's
    list taken as complete). Every message's work takes it as well: an old
    session's log line does not interleave with a new session's requeue of
    that job."""
    agent_id = _seed_agent(database)
    under_the_lock: list[bool] = []
    original = getattr(agents, step)

    def recording(*args, **kwargs):
        lock = agents._AGENT_SESSION_LOCKS.get(agent_id)
        under_the_lock.append(lock is not None and lock.locked())
        return original(*args, **kwargs)

    monkeypatch.setattr(agents, step, recording)
    with _connected(test_client) as websocket:
        _send_and_wait(websocket, handled, {"type": "heartbeat", "running_job_ids": []})

    # The hello's requeue and the heartbeat's
    expected = [True, True] if step == "_requeue_stale_agent_jobs" else [True]
    assert under_the_lock == expected


@pytest.mark.unit
def test_a_session_reads_the_agents_id_once(
    test_client, database, handled, monkeypatch
):
    """The agent's row expires with every commit: reading its id afterwards
    loaded the row again, on the loop, once per message."""
    agent_id = _seed_agent(database)
    job_id = _seed_job(database, agent_id)
    loads_on_the_loop = []

    def record(conn, cursor, statement, parameters, context, executemany):
        if "FROM agent_machines" in statement and _on_the_loop():
            loads_on_the_loop.append(statement)

    engine = database.kw["bind"]
    event.listen(engine, "before_cursor_execute", record)
    try:
        with _connected(test_client, running=[job_id]) as websocket:
            for _ in range(3):
                _send_and_wait(
                    websocket, handled, {**MESSAGES["progress"], "job_id": job_id}
                )
    finally:
        event.remove(engine, "before_cursor_execute", record)

    assert loads_on_the_loop == []


@pytest.mark.unit
def test_a_log_line_reaches_the_live_log_and_the_job_log(
    test_client, database, handled
):
    agent_id = _seed_agent(database)
    job_id = _seed_job(database, agent_id)

    with _connected(test_client, running=[job_id]) as websocket:
        _send_and_wait(websocket, handled, {**MESSAGES["log"], "job_id": job_id})

    assert _live_log(agent_id, job_id) == ["a line"]
    with database() as db:
        assert [row.message for row in db.query(AgentJobLog).all()] == ["a line"]


@pytest.mark.unit
def test_a_start_report_over_the_session_notifies_once(
    test_client, database, handled, monkeypatch
):
    agent_id = _seed_agent(database)
    operation_id, job_id = _seed_backup_job(database, agent_id)
    notified = []

    async def notify(db, job, backup_job):
        notified.append(job.id)

    monkeypatch.setattr(agents, "notify_backup_job_started", notify)
    with _connected(test_client, running=[job_id]) as websocket:
        for _ in range(2):
            _send_and_wait(
                websocket, handled, {"type": "job_started", "job_id": job_id}
            )

    assert notified == [job_id]
    assert _row(database, AgentJob, job_id).status == "running"
    assert _row(database, Operation, operation_id).status == "running"


@pytest.mark.unit
def test_a_session_holds_no_connection_while_it_waits_for_the_hello(
    test_client, database, monkeypatch
):
    """The hello may take seconds: the token check's read ends first."""
    _seed_agent(database)
    checked = threading.Event()
    original = agents._authenticate_session

    def telling(token, db):
        result = original(token, db)
        checked.set()
        return result

    monkeypatch.setattr(agents, "_authenticate_session", telling)
    engine = database.kw["bind"]
    with test_client.websocket_connect(
        "/api/agents/session",
        headers={"X-Borg-Agent-Authorization": f"Bearer {RAW_TOKEN}"},
    ) as websocket:
        assert checked.wait(HOLD_SECONDS)
        held_while_waiting = engine.pool.checkedout()
        websocket.send_json(_hello())
        assert websocket.receive_json()["type"] == "hello_ack"

    assert held_while_waiting == 0


@pytest.mark.unit
@pytest.mark.parametrize("when", ["hello", "heartbeat"])
def test_a_session_holds_no_connection_after_sending_queued_jobs(
    test_client, database, handled, monkeypatch, when
):
    agent_id = _seed_agent(database)
    sent = threading.Event()
    original = agents._send_queued_agent_jobs

    async def telling(db, jobs, *, source):
        await original(db, jobs, source=source)
        if jobs:
            sent.set()

    monkeypatch.setattr(agents, "_send_queued_agent_jobs", telling)
    engine = database.kw["bind"]
    queued_before = datetime(2026, 1, 1, tzinfo=timezone.utc)
    if when == "hello":
        job_id = _seed_job(database, agent_id, status="queued", claimed_at=None)
    with _connected(test_client) as websocket:
        if when == "heartbeat":
            job_id = _seed_job(
                database,
                agent_id,
                status="queued",
                claimed_at=None,
                created_at=queued_before,
            )
            websocket.send_json({"type": "heartbeat"})
        assert _receive(websocket)["job_id"] == job_id
        assert sent.wait(HOLD_SECONDS)
        held_after_sending = engine.pool.checkedout()

    assert held_after_sending == 0
    assert _row(database, AgentJob, job_id).status == "claimed"


@pytest.mark.unit
def test_a_message_the_session_ignores_holds_no_connection(
    test_client, database, monkeypatch
):
    agent_id = _seed_agent(database)
    checked = threading.Event()
    original = agents._check_session_agent

    def telling(db, agent_machine_id):
        original(db, agent_machine_id)
        checked.set()

    monkeypatch.setattr(agents, "_check_session_agent", telling)
    engine = database.kw["bind"]
    with _connected(test_client) as websocket:
        websocket.send_json(["not", "a", "message"])
        assert checked.wait(HOLD_SECONDS)
        held_after_it = engine.pool.checkedout()

    assert held_after_it == 0
    assert _row(database, AgentMachine, agent_id).status == "offline"


@pytest.mark.unit
def test_the_hello_ack_comes_before_any_command(test_client, database, monkeypatch):
    """A job dispatched to the session between its registration and its ack
    (registering closes the agent's previous session, which takes a turn of
    the loop) is sent once the ack is out."""
    agent_id = _seed_agent(database)
    gate = Gate()
    original_register = agent_connection_manager.register

    async def registered_then_held(connection):
        await original_register(connection)
        await asyncio.to_thread(gate.hold)

    monkeypatch.setattr(agent_connection_manager, "register", registered_then_held)
    sending = threading.Event()
    original_send = agent_connection_manager.send_command

    async def telling(*args, **kwargs):
        sending.set()
        return await original_send(*args, **kwargs)

    monkeypatch.setattr(agent_connection_manager, "send_command", telling)

    def dispatch(job_id: int) -> None:
        from app.services.agent_job_dispatcher import dispatch_agent_job_best_effort

        async def run():
            with database() as db:
                await dispatch_agent_job_best_effort(db, db.get(AgentJob, job_id))

        test_client.portal.call(run)

    with test_client.websocket_connect(
        "/api/agents/session",
        headers={"X-Borg-Agent-Authorization": f"Bearer {RAW_TOKEN}"},
    ) as websocket:
        websocket.send_json(_hello())
        assert gate.reached.wait(HOLD_SECONDS)
        job_id = _seed_job(database, agent_id, status="queued", claimed_at=None)
        with ThreadPoolExecutor(max_workers=1) as pool:
            dispatched = pool.submit(dispatch, job_id)
            assert sending.wait(HOLD_SECONDS)
            gate.open()
            frames = [_receive(websocket), _receive(websocket)]
            dispatched.result(HOLD_SECONDS)

    assert gate.opened_in_time == [True]
    assert [frame["type"] for frame in frames] == ["hello_ack", "command"]
    assert frames[1]["job_id"] == job_id


class _FakeWebSocket:
    """Just enough of a WebSocket for `session` called directly: the hello,
    then nothing until the task is cancelled."""

    def __init__(self, hello: dict) -> None:
        self.headers = {"X-Borg-Agent-Authorization": f"Bearer {RAW_TOKEN}"}
        self._frames = [hello]
        self.closed = None

    async def accept(self) -> None:
        pass

    async def receive_json(self) -> dict:
        if self._frames:
            return self._frames.pop(0)
        await asyncio.Event().wait()

    async def send_json(self, frame) -> None:
        pass

    async def close(self, code: int = 1000, reason: str = "") -> None:
        self.closed = code


@pytest.mark.unit
@pytest.mark.asyncio
async def test_a_session_cancelled_after_its_hello_leaves_the_agent_offline(
    test_db, monkeypatch
):
    """The hello marks the agent online in a thread, and the session is
    registered only after it. A session cancelled in between (the server
    shuts down) still takes the mark back."""
    sessions = sessionmaker(bind=test_db.get_bind())
    agent_id = _seed_agent(sessions, status="offline")
    gate = Gate()
    original = agents._record_session_hello

    def recorded_then_held(*args):
        result = original(*args)
        gate.hold()
        return result

    monkeypatch.setattr(agents, "_record_session_hello", recorded_then_held)
    db = sessions()
    try:
        task = asyncio.ensure_future(agents.session(_FakeWebSocket(_hello()), db))
        assert await asyncio.to_thread(gate.reached.wait, HOLD_SECONDS)
        assert _row(sessions, AgentMachine, agent_id).status == "online"
        task.cancel()
        gate.open()
        with pytest.raises(asyncio.CancelledError):
            await task
    finally:
        db.close()

    assert gate.opened_in_time == [True]
    assert not agent_connection_manager.is_connected(agent_id)
    assert _row(sessions, AgentMachine, agent_id).status == "offline"


@pytest.mark.unit
def test_a_replaced_session_leaves_its_successor_online(
    test_client, database, monkeypatch
):
    """A new session of the agent closes the old one. The new one does not
    wait for that close (its client may have stopped reading), and the old
    one's end must not mark the agent offline under the new one."""
    from app.services import agent_connection_manager as manager_module

    agent_id = _seed_agent(database, status="offline")
    first_gone = threading.Event()
    close_started = threading.Event()
    old_client_reads = threading.Event()
    old_closed = threading.Event()
    original_close = manager_module._close_replaced

    async def held_close(connection):
        close_started.set()
        # Only an explicit release closes: a gate that ran out does not.
        if await asyncio.to_thread(old_client_reads.wait, HOLD_SECONDS * 2):
            await original_close(connection)
            old_closed.set()

    monkeypatch.setattr(manager_module, "_close_replaced", held_close)
    original_disconnect = agent_connection_manager.disconnect
    sessions_seen = []

    async def telling(agent_machine_id, connection):
        result = await original_disconnect(agent_machine_id, connection)
        sessions_seen.append(result)
        first_gone.set()
        return result

    monkeypatch.setattr(agent_connection_manager, "disconnect", telling)

    async def after_the_old_sessions_end():
        # Its end holds the agent's lock from the disconnect to the mark.
        async with agents._agent_session_lock(agent_id):
            return agent_connection_manager.is_connected(agent_id)

    try:
        with _connected(test_client) as first:
            with _connected(test_client):
                # The new session got its ack while the old close is held.
                assert close_started.wait(HOLD_SECONDS)
                ack_while_held = not old_closed.is_set()
                old_client_reads.set()
                # The server closes the old session ...
                with pytest.raises(WebSocketDisconnect) as replaced:
                    _receive(first)
                # ... and its client goes too.
                with contextlib.suppress(Exception):
                    first.close()
                assert first_gone.wait(HOLD_SECONDS)
                connected = test_client.portal.call(after_the_old_sessions_end)
                status_meanwhile = _row(database, AgentMachine, agent_id).status
    finally:
        old_client_reads.set()

    assert ack_while_held
    assert replaced.value.code == 1012
    assert sessions_seen[0] is False
    assert connected
    assert status_meanwhile == "online"


@pytest.mark.unit
def test_a_session_ending_on_a_failed_message_marks_the_agent_offline(
    test_client, database
):
    """The failed message leaves its transaction to be rolled back; the
    offline mark at the session's end must not trip over it. PostgreSQL
    refuses the value at the flush; SQLite stores it."""
    if database.kw["bind"].dialect.name != "postgresql":
        pytest.skip("SQLite stores any value in an integer column")
    agent_id = _seed_agent(database, status="offline")
    job_id = _seed_job(database, agent_id)

    with pytest.raises(DBAPIError):
        with _connected(test_client, running=[job_id]) as websocket:
            websocket.send_json(
                {"type": "progress", "job_id": job_id, "nfiles": "not a count"}
            )
            _receive(websocket)

    assert _row(database, AgentMachine, agent_id).status == "offline"
    assert not agent_connection_manager.is_connected(agent_id)


@pytest.mark.unit
def test_a_session_holds_no_connection_after_its_start(
    test_client, database, monkeypatch
):
    """The reads at the start (owed cancels, queued jobs) end before the
    session waits for its first message."""
    agent_id = _seed_agent(database)
    job_id = _seed_job(database, agent_id, status="cancel_requested")
    read = threading.Event()
    original = agents._jobs_owed_at_hello

    def telling(*args):
        result = original(*args)
        read.set()
        return result

    monkeypatch.setattr(agents, "_jobs_owed_at_hello", telling)
    engine = database.kw["bind"]
    with _connected(test_client, running=[job_id]) as websocket:
        assert read.wait(HOLD_SECONDS)
        held_after_the_start = engine.pool.checkedout()
        assert _receive(websocket)["command"] == "cancel"

    assert held_after_the_start == 0


@pytest.mark.unit
def test_nothing_is_sent_to_an_agent_revoked_after_its_hello(
    test_client, database, monkeypatch
):
    agent_id = _seed_agent(database)
    job_id = _seed_job(database, agent_id, status="queued", claimed_at=None)
    original = agents._record_session_hello

    def revoked_after_the_hello(*args):
        result = original(*args)
        _set_columns(database, AgentMachine, agent_id, {"status": "revoked"})
        return result

    monkeypatch.setattr(agents, "_record_session_hello", revoked_after_the_hello)

    with pytest.raises(WebSocketDisconnect) as closed:
        with test_client.websocket_connect(
            "/api/agents/session",
            headers={"X-Borg-Agent-Authorization": f"Bearer {RAW_TOKEN}"},
        ) as websocket:
            websocket.send_json(_hello())
            assert _receive(websocket)["type"] == "hello_ack"
            _receive(websocket)

    assert closed.value.code == 1008
    assert _row(database, AgentJob, job_id).status == "queued"
    assert _row(database, AgentMachine, agent_id).status == "revoked"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_a_failed_message_gives_up_its_locks_before_the_agents_lock(
    test_db, monkeypatch
):
    """A message that fails after a write ends its transaction in its own
    thread. Left open, its write lock would outlive the agent's session
    lock: a new session's hello would take that lock and wait for the write
    lock, while this session's end waited for the agent's lock."""
    sessions = sessionmaker(bind=test_db.get_bind())
    agent_id = _seed_agent(sessions)
    job_id = _seed_job(sessions, agent_id)

    def written_then_failed(job, db, progress):
        db.query(AgentJob).filter(AgentJob.id == job.id).update(
            {AgentJob.nfiles: 1}, synchronize_session=False
        )
        raise RuntimeError("the message failed after its write")

    monkeypatch.setattr(agents, "_apply_agent_job_progress", written_then_failed)
    db = sessions()
    try:
        with pytest.raises(RuntimeError):
            await agents._handle_agent_session_message(
                db,
                agent_id,
                {**MESSAGES["progress"], "job_id": job_id},
                check_active=True,
            )
        in_transaction = db.in_transaction()
    finally:
        db.close()

    assert in_transaction is False
    # Nothing holds SQLite's write lock: another writer gets it at once.
    other = test_db.get_bind().connect()
    try:
        other.exec_driver_sql("PRAGMA busy_timeout=0")
        other.exec_driver_sql("BEGIN IMMEDIATE")
        other.exec_driver_sql("ROLLBACK")
    finally:
        other.close()


@pytest.mark.unit
def test_a_session_ending_on_a_failed_start_read_marks_the_agent_offline(
    test_client, database, monkeypatch
):
    """A read that fails ends no transaction of its own; the offline mark at
    the session's end starts from a clean one. PostgreSQL aborts the
    transaction on the error; SQLite does not fail the statement."""
    if database.kw["bind"].dialect.name != "postgresql":
        pytest.skip("SQLite answers 1/0 with NULL")
    agent_id = _seed_agent(database, status="offline")

    def failing_read(db, agent_machine_id, running_job_ids):
        db.execute(text("SELECT 1/0"))

    monkeypatch.setattr(agents, "_cancel_requested_running_jobs", failing_read)

    with pytest.raises(DBAPIError):
        with test_client.websocket_connect(
            "/api/agents/session",
            headers={"X-Borg-Agent-Authorization": f"Bearer {RAW_TOKEN}"},
        ) as websocket:
            websocket.send_json(_hello())
            assert _receive(websocket)["type"] == "hello_ack"
            _receive(websocket)

    assert _row(database, AgentMachine, agent_id).status == "offline"
    assert not agent_connection_manager.is_connected(agent_id)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_registering_does_not_wait_for_a_replaced_session_that_hangs():
    """The new session registers under the agent's lock; a replaced client
    that stopped reading must not keep it there. The old session is still
    closed, once its client reads again."""
    from app.services.agent_connection_manager import (
        AgentConnection,
        AgentConnectionManager,
    )

    class GatedClose(_FakeWebSocket):
        def __init__(self, hello: dict) -> None:
            super().__init__(hello)
            self.reading = asyncio.Event()
            self.closed_with = asyncio.Event()

        async def close(self, code: int = 1000, reason: str = "") -> None:
            await self.reading.wait()
            self.closed = code
            self.closed_with.set()

    manager = AgentConnectionManager()
    old_socket = GatedClose(_hello())
    old = AgentConnection(agent_machine_id=7, agent_id=AGENT_ID, websocket=old_socket)
    new = AgentConnection(
        agent_machine_id=7, agent_id=AGENT_ID, websocket=_FakeWebSocket(_hello())
    )
    await manager.register(old)

    await asyncio.wait_for(manager.register(new), HOLD_SECONDS)
    registered_before_the_close = old_socket.closed is None

    old_socket.reading.set()
    await asyncio.wait_for(old_socket.closed_with.wait(), HOLD_SECONDS)

    assert registered_before_the_close
    assert manager.get(7) is new
    assert old_socket.closed == 1012
