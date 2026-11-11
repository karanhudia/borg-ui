"""The agent endpoints off the event loop.

A handler on the loop ran from its read to its commit with nothing in between.
In a worker thread the requests around it keep running, so a write it shares
with another request has to decide on the row, not on the copy it read.

The races are laid out with real requests on a session each: a `Gate` stops one
request after its read while the other commits. With a handler back on the loop
the held request stops every other request as well, the gate runs out, and the
test fails after HOLD_SECONDS instead of hanging. No test depends on how long
anything takes.

The races run on SQLite and, with BORG_TEST_POSTGRES_URL set, on PostgreSQL:
SQLite takes one writer at a time, PostgreSQL decides on row locks.
"""

import asyncio
import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from anyio import CancelScope, to_thread
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import QueuePool

import app.api.agents as agents
from app.api.agents import AgentJobStartRequest
from app.database.database import Base, get_db, register_utc_session_timezone
from app.database.models import (
    AgentEnrollmentToken,
    AgentJob,
    AgentMachine,
    Operation,
    Repository,
)
from app.services.operations.backup_facade import BackupJobFacade
from app.utils.datetime_utils import utc_now
from tests.utils.agent_jobs import agent_maintenance_job
from tests.utils.operations import seed_job_operation

POSTGRES_URL = os.getenv("BORG_TEST_POSTGRES_URL")
RAW_TOKEN = "borgui_agent_" + "e" * 43
ENROLLMENT_TOKEN = "borgui_enroll_" + "k" * 43
AGENT_ID = "agt_endpoints"
# Long enough for a request to arrive, short enough that a handler held on the
# loop fails the test instead of hanging it.
HOLD_SECONDS = 5
REGISTRATIONS = 4
PROGRESS = {"progress_percent": 97.5, "total_expected_size": 1000, "nfiles": 7}
FINAL_NFILES = 10
COMPLETION = {
    "result": {
        "return_code": 0,
        "archive_name": "race-archive",
        "archive_stats": {"original_size": 1000, "nfiles": FINAL_NFILES},
    }
}


class Gate:
    """Stops the first thread that reaches it until the test opens it."""

    def __init__(self) -> None:
        self.reached = threading.Event()
        self.opened_in_time: list[bool] = []
        self._opened = threading.Event()
        self._lock = threading.Lock()
        self._taken = False

    def hold(self) -> None:
        with self._lock:
            if self._taken:
                return
            self._taken = True
        self.reached.set()
        self.opened_in_time.append(self._opened.wait(HOLD_SECONDS))

    def open(self) -> None:
        self._opened.set()


def _hold_after(monkeypatch, name: str, gate: Gate) -> None:
    original = getattr(agents, name)

    def held(*args, **kwargs):
        result = original(*args, **kwargs)
        gate.hold()
        return result

    monkeypatch.setattr(agents, name, held)


def _while_held(gate: Gate, request, meanwhile):
    """Run `request` in a thread and `meanwhile` while the gate holds it. The
    gate has to be opened in time: `meanwhile` did not wait for `request`."""
    with ThreadPoolExecutor(max_workers=1) as pool:
        held = pool.submit(request)
        assert gate.reached.wait(HOLD_SECONDS), "the request never reached the gate"
        other = meanwhile()
        gate.open()
        result = held.result(HOLD_SECONDS * 2)
    assert gate.opened_in_time == [True]
    return result, other


def _on_the_loop() -> bool:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return False
    return True


@contextmanager
def _postgres_sessions():
    """A schema of its own: the other PostgreSQL tests drop `public`."""
    schema = f"agent_endpoints_{uuid.uuid4().hex}"
    admin = create_engine(POSTGRES_URL)
    with admin.begin() as conn:
        conn.execute(text(f"CREATE SCHEMA {schema}"))
    engine = create_engine(
        POSTGRES_URL, connect_args={"options": f"-c search_path={schema}"}
    )
    register_utc_session_timezone(engine)
    try:
        Base.metadata.create_all(engine)
        yield sessionmaker(autocommit=False, autoflush=False, bind=engine)
    finally:
        engine.dispose()
        with admin.begin() as conn:
            conn.execute(text(f"DROP SCHEMA {schema} CASCADE"))
        admin.dispose()


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


@pytest.fixture(autouse=True)
def agent_tokens_pass(monkeypatch):
    monkeypatch.setattr(
        "app.core.agent_auth.verify_password", lambda token, token_hash: True
    )


def _post(client, path: str, body=None):
    return client.post(
        path,
        json=body,
        headers={"X-Borg-Agent-Authorization": f"Bearer {RAW_TOKEN}"},
    )


def _job_path(job_id: int, action: str) -> str:
    return f"/api/agents/jobs/{job_id}/{action}"


def _seed_agent(sessions) -> int:
    with sessions() as db:
        agent = AgentMachine(
            name="Endpoint Agent",
            agent_id=AGENT_ID,
            token_hash="checked by the test's stand-in",
            token_prefix=RAW_TOKEN[:20],
            status="online",
            capabilities=["session.commands"],
        )
        db.add(agent)
        db.commit()
        return agent.id


def _seed_job(sessions, agent_id: int, *, status: str = "queued", **columns) -> int:
    with sessions() as db:
        job = AgentJob(
            agent_machine_id=agent_id,
            job_type="repository",
            status=status,
            payload={"job_kind": "repository.delete_archive"},
            **columns,
        )
        db.add(job)
        db.commit()
        return job.id


def _seed_idle_job(sessions, agent_id: int, *, status: str = "running") -> int:
    """A job that has been silent for longer than the requeue waits."""
    idle = utc_now() - agents.STALE_AGENT_JOB_REQUEUE_AFTER - timedelta(minutes=1)
    return _seed_job(
        sessions,
        agent_id,
        status=status,
        claimed_at=idle,
        started_at=idle,
        updated_at=idle,
    )


def _seed_backup_job(sessions, agent_id: int, *, status: str) -> tuple[int, int]:
    """A backup handed to the agent, `running` or with its start not reported.
    Returns the operation's id and the agent job's."""
    now = datetime.now(timezone.utc)
    started = now if status == "running" else None
    with sessions() as db:
        operation = seed_job_operation(
            db, "backup", repository="/endpoints", status="running", started_at=now
        )
        db.commit()
        job = AgentJob(
            agent_machine_id=agent_id,
            job_type="backup",
            status=status,
            payload={
                "schema_version": 1,
                "job_kind": "backup.create",
                "repository": {"id": operation.repository_id},
            },
            operation_id=operation.id,
            claimed_at=now,
            started_at=started,
            start_notified_at=started,
        )
        db.add(job)
        db.commit()
        return operation.id, job.id


def _seed_compact_job(sessions, agent_id: int) -> tuple[int, int]:
    """A running compact. Returns the operation's id and the agent job's."""
    now = datetime.now(timezone.utc)
    with sessions() as db:
        repository = Repository(name="endpoints", path="/endpoints-compact")
        db.add(repository)
        db.commit()
        operation = Operation(
            repository_id=repository.id,
            kind="compact",
            category="maintenance",
            status="running",
            trigger="manual",
            priority=10,
            run_id="run-endpoints",
            started_at=now,
        )
        db.add(operation)
        db.commit()
        job = agent_maintenance_job(
            db,
            db.get(AgentMachine, agent_id),
            "compact",
            operation.id,
            repository=repository,
            status="running",
            claimed_at=now,
            started_at=now,
            start_notified_at=now,
            created_at=now,
            updated_at=now,
        )
        return operation.id, job.id


def _seed_enrollment_token(sessions, **columns) -> int:
    with sessions() as db:
        token = AgentEnrollmentToken(
            name="one use",
            token_hash="checked by the test's stand-in",
            token_prefix=ENROLLMENT_TOKEN[:20],
            **columns,
        )
        db.add(token)
        db.commit()
        return token.id


def _set_columns(sessions, model, row_id: int, values: dict) -> None:
    """Commit a change the way another request would."""
    with sessions() as db:
        db.query(model).filter(model.id == row_id).update(
            values, synchronize_session=False
        )
        db.commit()


def _register(client, name: str = "laptop"):
    return client.post(
        "/api/agents/register",
        json={"enrollment_token": ENROLLMENT_TOKEN, "name": name},
    )


def _agent_ids(sessions) -> list[str]:
    with sessions() as db:
        return [row.agent_id for row in db.query(AgentMachine).all()]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("path", "body", "held_write"),
    [
        pytest.param(
            "/api/agents/heartbeat",
            {"agent_id": AGENT_ID},
            "UPDATE agent_machines",
            id="heartbeat",
        ),
        pytest.param(
            "/api/agents/unregister",
            None,
            "UPDATE agent_machines",
            id="unregister",
        ),
        pytest.param(
            "/api/agents/jobs/{job}/claim", None, "UPDATE agent_jobs", id="claim"
        ),
        pytest.param(
            "/api/agents/jobs/{job}/start", {}, "UPDATE agent_jobs", id="start"
        ),
        pytest.param(
            "/api/agents/jobs/{job}/progress",
            PROGRESS,
            "UPDATE agent_jobs",
            id="progress",
        ),
        pytest.param(
            "/api/agents/register",
            {"enrollment_token": ENROLLMENT_TOKEN, "name": "laptop"},
            "INSERT INTO agent_machines",
            id="register",
        ),
    ],
)
def test_the_loop_answers_while_an_endpoint_writes(
    test_client, test_db, session_per_request, monkeypatch, path, body, held_write
):
    agent_id = _seed_agent(session_per_request)
    job_id = _seed_job(session_per_request, agent_id)
    _seed_enrollment_token(session_per_request)
    monkeypatch.setattr(
        "app.api.agents.verify_password", lambda token, token_hash: True
    )
    gate = Gate()
    writes_on_the_loop = []

    def on_write(conn, cursor, statement, parameters, context, executemany):
        if not statement.startswith(("INSERT INTO agent_", "UPDATE agent_")):
            return
        if _on_the_loop():
            writes_on_the_loop.append(statement)
        if statement.startswith(held_write):
            gate.hold()

    engine = test_db.get_bind()
    event.listen(engine, "before_cursor_execute", on_write)
    try:
        response, health = _while_held(
            gate,
            lambda: _post(test_client, path.format(job=job_id), body),
            lambda: test_client.get("/health"),
        )
    finally:
        event.remove(engine, "before_cursor_execute", on_write)

    assert health.status_code == 200
    assert response.status_code < 300
    assert writes_on_the_loop == []


@pytest.mark.unit
def test_a_claim_loses_to_a_cancel_reported_after_its_read(
    test_client, database, monkeypatch
):
    job_id = _seed_job(database, _seed_agent(database))
    gate = Gate()
    _hold_after(monkeypatch, "_get_agent_job", gate)

    claim, cancel = _while_held(
        gate,
        lambda: _post(test_client, _job_path(job_id, "claim")),
        lambda: _post(test_client, _job_path(job_id, "cancel"), {}),
    )

    assert cancel.status_code == 200
    assert claim.status_code == 409
    assert claim.json()["detail"]["key"] == "backend.errors.agents.jobAlreadyFinished"
    with database() as db:
        job = db.get(AgentJob, job_id)
        assert job.status == "canceled"
        assert job.claimed_at is None


@pytest.mark.unit
def test_a_claim_keeps_a_cancel_request_committed_after_its_read(
    test_client, database, monkeypatch
):
    """A user's cancel of a queued job is a request, not a final status: the
    claim does not take it back, and the agent reads it from the answer."""
    job_id = _seed_job(database, _seed_agent(database))
    gate = Gate()
    _hold_after(monkeypatch, "_get_agent_job", gate)

    claim, _ = _while_held(
        gate,
        lambda: _post(test_client, _job_path(job_id, "claim")),
        lambda: _set_columns(
            database, AgentJob, job_id, {"status": "cancel_requested"}
        ),
    )

    assert claim.status_code == 200
    assert claim.json()["status"] == "cancel_requested"
    with database() as db:
        job = db.get(AgentJob, job_id)
        assert job.status == "cancel_requested"
        assert job.claimed_at is None


@pytest.mark.unit
def test_a_progress_report_read_before_a_completion_keeps_the_verdict(
    test_client, database, monkeypatch
):
    agent_id = _seed_agent(database)
    operation_id, job_id = _seed_backup_job(database, agent_id, status="running")
    gate = Gate()
    _hold_after(monkeypatch, "_get_agent_job", gate)

    report, completion = _while_held(
        gate,
        lambda: _post(test_client, _job_path(job_id, "progress"), PROGRESS),
        lambda: _post(test_client, _job_path(job_id, "complete"), COMPLETION),
    )

    assert completion.json()["status"] == "completed"
    # the answer reads the job as the completion left it
    assert report.status_code == 200
    assert report.json()["status"] == "completed"
    with database() as db:
        job = db.get(AgentJob, job_id)
        assert job.status == "completed"
        assert job.nfiles == FINAL_NFILES
        assert db.get(Operation, operation_id).status == "completed"


@pytest.mark.unit
def test_a_completion_during_a_progress_report_lands_after_it(
    test_client, database, monkeypatch
):
    """The other order: the report holds the row, so the completion waits for
    its commit and then writes its verdict and counters over the report's."""
    agent_id = _seed_agent(database)
    operation_id, job_id = _seed_backup_job(database, agent_id, status="running")
    gate = Gate()
    _hold_after(monkeypatch, "_claim_progress_write", gate)
    at_terminal_write = threading.Event()
    original = agents._claim_terminal_transition

    def reach_terminal_write(*args, **kwargs):
        at_terminal_write.set()
        return original(*args, **kwargs)

    monkeypatch.setattr(agents, "_claim_terminal_transition", reach_terminal_write)

    with ThreadPoolExecutor(max_workers=2) as pool:
        report = pool.submit(
            _post, test_client, _job_path(job_id, "progress"), PROGRESS
        )
        assert gate.reached.wait(HOLD_SECONDS)
        completion = pool.submit(
            _post, test_client, _job_path(job_id, "complete"), COMPLETION
        )
        assert at_terminal_write.wait(HOLD_SECONDS)
        gate.open()
        assert report.result(HOLD_SECONDS * 2).status_code == 200
        assert completion.result(HOLD_SECONDS * 2).json()["status"] == "completed"

    assert gate.opened_in_time == [True]
    with database() as db:
        job = db.get(AgentJob, job_id)
        assert job.status == "completed"
        assert job.nfiles == FINAL_NFILES
        assert db.get(Operation, operation_id).status == "completed"


@pytest.mark.unit
def test_a_keepalive_read_before_a_report_leaves_its_counters(
    test_client, database, monkeypatch
):
    """A keepalive carries no figures and passes on what the job holds, which
    is the report's by the time it gets the row, not what it read."""
    agent_id = _seed_agent(database)
    operation_id, job_id = _seed_backup_job(database, agent_id, status="running")
    gate = Gate()
    _hold_after(monkeypatch, "_get_agent_job", gate)

    keepalive, report = _while_held(
        gate,
        lambda: _post(test_client, _job_path(job_id, "progress"), {}),
        lambda: _post(test_client, _job_path(job_id, "progress"), PROGRESS),
    )

    assert report.status_code == 200
    assert keepalive.status_code == 200
    with database() as db:
        assert db.get(AgentJob, job_id).nfiles == PROGRESS["nfiles"]
        backup = BackupJobFacade(db, db.get(Operation, operation_id))
        assert backup.nfiles == PROGRESS["nfiles"]


@contextmanager
def _agent_session(client, monkeypatch):
    """An open session, and the event set once a message was handled."""
    handled = threading.Event()
    original = agents._handle_agent_session_message

    async def handle_and_tell(*args, **kwargs):
        await original(*args, **kwargs)
        handled.set()

    monkeypatch.setattr(agents, "_handle_agent_session_message", handle_and_tell)
    with client.websocket_connect(
        "/api/agents/session",
        headers={"X-Borg-Agent-Authorization": f"Bearer {RAW_TOKEN}"},
    ) as websocket:
        websocket.send_json(
            {
                "type": "hello",
                "agent_id": AGENT_ID,
                "hostname": "session.local",
                "agent_version": "0.2.0",
                "borg_versions": [],
                "capabilities": ["session.commands"],
                "running_job_ids": [],
            }
        )
        assert websocket.receive_json()["type"] == "hello_ack"
        yield websocket, handled


@pytest.mark.unit
def test_a_claim_on_both_transports_keeps_the_first_claims_time(
    test_client, database, monkeypatch
):
    """The claim time names the agent's run, so the loser must not rewrite it."""
    agent_id = _seed_agent(database)

    with _agent_session(test_client, monkeypatch) as (websocket, handled):
        # Seeded after the hello: the session's start sends what is queued.
        job_id = _seed_job(database, agent_id)
        gate = Gate()
        _hold_after(monkeypatch, "_get_agent_job", gate)

        def acknowledge():
            websocket.send_json({"type": "command_ack", "job_id": job_id})
            assert handled.wait(HOLD_SECONDS)
            with database() as db:
                return db.get(AgentJob, job_id).claimed_at

        claim, claimed_at = _while_held(
            gate,
            lambda: _post(test_client, _job_path(job_id, "claim")),
            acknowledge,
        )

    assert claimed_at is not None
    assert claim.status_code == 200
    assert claim.json()["status"] == "claimed"
    with database() as db:
        assert db.get(AgentJob, job_id).claimed_at == claimed_at


@pytest.mark.unit
@pytest.mark.parametrize(
    "landed",
    [
        pytest.param({"status": "canceled"}, id="cancel"),
        pytest.param(
            {"status": "claimed", "claimed_at": datetime(2026, 11, 7, 12, 0)},
            id="rest-claim",
        ),
    ],
)
def test_a_session_claim_leaves_what_landed_after_its_read(
    test_client, database, monkeypatch, landed
):
    agent_id = _seed_agent(database)

    with _agent_session(test_client, monkeypatch) as (websocket, handled):
        job_id = _seed_job(database, agent_id)
        original = agents._load_session_job

        def write_lands(db, agent_machine_id, message_job_id):
            loaded = original(db, agent_machine_id, message_job_id)
            _set_columns(database, AgentJob, job_id, landed)
            return loaded

        monkeypatch.setattr(agents, "_load_session_job", write_lands)
        websocket.send_json({"type": "command_ack", "job_id": job_id})
        assert handled.wait(HOLD_SECONDS)

    with database() as db:
        job = db.get(AgentJob, job_id)
        assert job.status == landed["status"]
        assert job.claimed_at == landed.get("claimed_at")


@pytest.mark.unit
def test_a_session_claim_still_claims_a_queued_job(test_client, database, monkeypatch):
    agent_id = _seed_agent(database)

    with _agent_session(test_client, monkeypatch) as (websocket, handled):
        job_id = _seed_job(database, agent_id)
        websocket.send_json({"type": "command_ack", "job_id": job_id})
        assert handled.wait(HOLD_SECONDS)

    with database() as db:
        job = db.get(AgentJob, job_id)
        assert job.status == "claimed"
        assert job.claimed_at is not None


@pytest.mark.unit
def test_the_usual_acknowledgement_writes_nothing(
    test_client, test_db, session_per_request, monkeypatch
):
    """The dispatch claimed the job before it sent it. Even an UPDATE that
    matches no row waits for SQLite's write lock, and the session handler runs
    on the loop, so every other request would wait with it."""
    agent_id = _seed_agent(session_per_request)
    writes = []

    def on_write(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("UPDATE agent_jobs"):
            writes.append(statement)

    engine = test_db.get_bind()
    with _agent_session(test_client, monkeypatch) as (websocket, handled):
        job_id = _seed_job(session_per_request, agent_id, status="claimed")
        event.listen(engine, "before_cursor_execute", on_write)
        try:
            websocket.send_json({"type": "command_ack", "job_id": job_id})
            assert handled.wait(HOLD_SECONDS)
        finally:
            event.remove(engine, "before_cursor_execute", on_write)

    assert writes == []


@pytest.mark.unit
def test_one_enrollment_token_enrolls_one_agent(test_client, database, monkeypatch):
    token_id = _seed_enrollment_token(database)
    all_checking = threading.Barrier(REGISTRATIONS, timeout=HOLD_SECONDS)

    def meeting_check(token, token_hash):
        all_checking.wait()
        return True

    monkeypatch.setattr("app.api.agents.verify_password", meeting_check)

    with ThreadPoolExecutor(max_workers=REGISTRATIONS) as pool:
        responses = list(
            pool.map(
                lambda number: _register(test_client, f"laptop-{number}"),
                range(REGISTRATIONS),
            )
        )

    codes = sorted(response.status_code for response in responses)
    assert codes == [200] + [401] * (REGISTRATIONS - 1)
    winner = next(r for r in responses if r.status_code == 200).json()
    for refused in (r for r in responses if r.status_code == 401):
        assert (
            refused.json()["detail"]["key"]
            == "backend.errors.agents.invalidEnrollmentToken"
        )
    assert _agent_ids(database) == [winner["agent_id"]]
    with database() as db:
        token = db.get(AgentEnrollmentToken, token_id)
        agent = db.query(AgentMachine).one()
        assert token.used_by_agent_id == agent.id
        assert token.used_at is not None


@pytest.mark.unit
@pytest.mark.parametrize(
    "column", ["used_at", "revoked_at", "expires_at"], ids=lambda column: column
)
def test_a_token_that_stopped_being_valid_during_its_check_enrolls_nobody(
    test_client, database, monkeypatch, column
):
    token_id = _seed_enrollment_token(database)
    gate = Gate()

    def held_check(token, token_hash):
        gate.hold()
        return True

    monkeypatch.setattr("app.api.agents.verify_password", held_check)

    response, _ = _while_held(
        gate,
        lambda: _register(test_client),
        lambda: _set_columns(
            database,
            AgentEnrollmentToken,
            token_id,
            {column: utc_now() - timedelta(minutes=1)},
        ),
    )

    assert response.status_code == 401
    assert _agent_ids(database) == []


@pytest.mark.unit
def test_a_token_that_expires_while_the_agent_token_is_hashed_enrolls_nobody(
    test_client, database, monkeypatch
):
    """Nothing writes to the token here: its time runs out between the check
    and the consume, which the agent's token takes bcrypt to fill."""
    clock = [datetime.now(timezone.utc)]
    token_id = _seed_enrollment_token(
        database,
        expires_at=(clock[0] + timedelta(seconds=1)).replace(tzinfo=None),
    )

    def hash_and_let_time_pass(token):
        clock[0] += timedelta(seconds=2)
        return "hash"

    monkeypatch.setattr(agents, "_now_utc", lambda: clock[0])
    monkeypatch.setattr(agents, "get_password_hash", hash_and_let_time_pass)
    monkeypatch.setattr(
        "app.api.agents.verify_password", lambda token, token_hash: True
    )

    response = _register(test_client)

    assert response.status_code == 401
    assert _agent_ids(database) == []
    with database() as db:
        assert db.get(AgentEnrollmentToken, token_id).used_at is None


@pytest.mark.unit
def test_a_token_with_time_left_enrolls(test_client, database, monkeypatch):
    token_id = _seed_enrollment_token(
        database, expires_at=utc_now() + timedelta(minutes=1)
    )
    monkeypatch.setattr(
        "app.api.agents.verify_password", lambda token, token_hash: True
    )

    response = _register(test_client)

    assert response.status_code == 200
    with database() as db:
        assert db.get(AgentEnrollmentToken, token_id).used_at is not None


@pytest.mark.unit
def test_a_start_report_read_before_a_completion_leaves_the_job_final(
    test_client, database, monkeypatch
):
    agent_id = _seed_agent(database)
    operation_id, job_id = _seed_backup_job(database, agent_id, status="claimed")
    notify = AsyncMock()
    monkeypatch.setattr(agents, "notify_backup_job_started", notify)
    gate = Gate()
    _hold_after(monkeypatch, "_get_agent_job", gate)

    start, completion = _while_held(
        gate,
        lambda: _post(test_client, _job_path(job_id, "start"), {}),
        lambda: _post(test_client, _job_path(job_id, "complete"), COMPLETION),
    )

    assert completion.json()["status"] == "completed"
    assert start.status_code == 200
    assert start.json()["status"] == "completed"
    notify.assert_not_awaited()
    with database() as db:
        assert db.get(AgentJob, job_id).status == "completed"
        assert db.get(Operation, operation_id).status == "completed"


@pytest.mark.unit
def test_a_start_report_read_before_a_dispatch_keeps_the_claim_time(
    test_client, database, monkeypatch
):
    """The claim time names the agent's run: rewritten, the lines the agent
    sends for it are taken for another run's and dropped."""
    job_id = _seed_job(database, _seed_agent(database))
    dispatched_at = datetime(2026, 11, 7, 12, 0)
    gate = Gate()
    _hold_after(monkeypatch, "_get_agent_job", gate)

    start, _ = _while_held(
        gate,
        lambda: _post(test_client, _job_path(job_id, "start"), {}),
        lambda: _set_columns(
            database,
            AgentJob,
            job_id,
            {"status": "claimed", "claimed_at": dispatched_at},
        ),
    )

    assert start.json()["status"] == "running"
    with database() as db:
        assert db.get(AgentJob, job_id).claimed_at == dispatched_at


@pytest.mark.unit
def test_a_start_report_read_before_a_progress_report_passes_on_the_row(
    test_client, database, monkeypatch
):
    """A start report syncs the operation from the job, so it has to pass on
    the figures of a report committed since its read, not take them back."""
    agent_id = _seed_agent(database)
    operation_id, job_id = _seed_compact_job(database, agent_id)
    gate = Gate()
    _hold_after(monkeypatch, "_get_agent_job", gate)

    start, report = _while_held(
        gate,
        lambda: _post(test_client, _job_path(job_id, "start"), {}),
        lambda: _post(test_client, _job_path(job_id, "progress"), PROGRESS),
    )

    assert report.status_code == 200
    assert start.status_code == 200
    with database() as db:
        assert db.get(AgentJob, job_id).nfiles == PROGRESS["nfiles"]
        operation = db.get(Operation, operation_id)
        assert operation.progress_percent == int(PROGRESS["progress_percent"])


@pytest.mark.unit
def test_two_start_reports_notify_once(test_client, database, monkeypatch):
    agent_id = _seed_agent(database)
    operation_id, job_id = _seed_backup_job(database, agent_id, status="claimed")
    notify = AsyncMock()
    monkeypatch.setattr(agents, "notify_backup_job_started", notify)
    both_read = threading.Barrier(2, timeout=HOLD_SECONDS)
    original = agents._get_agent_job

    def read_then_meet(*args, **kwargs):
        loaded = original(*args, **kwargs)
        both_read.wait()
        return loaded

    monkeypatch.setattr(agents, "_get_agent_job", read_then_meet)

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(
            pool.map(
                lambda minute: _post(
                    test_client,
                    _job_path(job_id, "start"),
                    {"started_at": f"2026-11-07T12:0{minute}:00Z"},
                ),
                range(2),
            )
        )

    assert [response.status_code for response in responses] == [200, 200]
    assert [response.json()["status"] for response in responses] == ["running"] * 2
    assert notify.await_count == 1
    assert notify.await_args.args[2].id == operation_id
    # The report that lost keeps its hands off the winner's start time.
    with database() as db:
        started_at = db.get(AgentJob, job_id).started_at
        assert started_at == db.get(Operation, operation_id).started_at


@pytest.mark.unit
async def test_a_dropped_start_report_still_notifies(session_per_request, monkeypatch):
    """The agent drops a request after 30 s while the worker is still
    committing, and its retry finds the start recorded: the notification of
    the first report must not depend on the request still awaiting."""
    agent_id = _seed_agent(session_per_request)
    _, job_id = _seed_backup_job(session_per_request, agent_id, status="claimed")
    notified = asyncio.Event()

    async def notify(db, job, backup_job):
        notified.set()

    monkeypatch.setattr(agents, "notify_backup_job_started", notify)
    gate = Gate()
    _hold_after(monkeypatch, "_get_agent_job", gate)

    request = asyncio.ensure_future(
        agents.start_job(
            job_id,
            AgentJobStartRequest(),
            current_agent=SimpleNamespace(id=agent_id),
            db=MagicMock(),
        )
    )
    assert await asyncio.to_thread(gate.reached.wait, HOLD_SECONDS)
    request.cancel()
    with pytest.raises(asyncio.CancelledError):
        await request
    gate.open()

    await asyncio.wait_for(notified.wait(), timeout=HOLD_SECONDS)
    await asyncio.gather(*agents._REPORT_TASKS)
    with session_per_request() as db:
        assert db.get(AgentJob, job_id).status == "running"


@pytest.mark.unit
async def test_a_start_report_gives_back_its_connection_before_its_worker_runs(
    test_db, session_per_request
):
    """The worker takes a connection of its own. With the request's idle read
    still open, a burst of reports holds the whole pool and waits for it, and
    every report fails at the pool's timeout. A pool of one shows that for a
    single report: the worker gets the connection only if the request gave it
    back."""
    agent_id = _seed_agent(session_per_request)
    job_id = _seed_job(session_per_request, agent_id, status="claimed")
    engine = create_engine(
        test_db.get_bind().url,
        poolclass=QueuePool,
        pool_size=1,
        max_overflow=0,
        pool_timeout=HOLD_SECONDS,
        connect_args={"check_same_thread": False},
    )
    sessions = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    request_db = sessions()
    original_rollback = request_db.rollback
    rollbacks_on_the_loop = []

    def recorded_rollback():
        rollbacks_on_the_loop.append(_on_the_loop())
        original_rollback()

    request_db.rollback = recorded_rollback
    try:
        # The token lookup of the request, which leaves its read open.
        agent = request_db.get(AgentMachine, agent_id)
        with patch("app.database.database.SessionLocal", sessions):
            response = await agents.start_job(
                job_id, AgentJobStartRequest(), current_agent=agent, db=request_db
            )
    finally:
        request_db.close()
        engine.dispose()

    assert response.status == "running"
    assert rollbacks_on_the_loop == [False]


@pytest.mark.unit
async def test_a_start_report_gives_back_its_connection_without_a_shared_token(
    session_per_request,
):
    """The shared worker tokens can all be with requests that wait for a
    connection. Waiting for one while holding a connection would be that same
    wait, so the release must not need one."""
    agent_id = _seed_agent(session_per_request)
    job_id = _seed_job(session_per_request, agent_id, status="claimed")
    limiter = to_thread.current_default_thread_limiter()
    total_tokens = limiter.total_tokens
    limiter.total_tokens = 1
    await limiter.acquire()
    try:
        response = await asyncio.wait_for(
            agents.start_job(
                job_id,
                AgentJobStartRequest(),
                current_agent=SimpleNamespace(id=agent_id),
                db=MagicMock(),
            ),
            timeout=HOLD_SECONDS,
        )
    finally:
        limiter.release()
        limiter.total_tokens = total_tokens

    assert response.status == "running"


@pytest.mark.unit
@pytest.mark.parametrize("cancelled_by", ["a cancel scope", "the task"])
async def test_a_cancelled_start_report_waits_for_its_release(
    session_per_request, cancelled_by
):
    """The session is closed with the request, so the thread that ends its read
    has to be done by then. Nothing is recorded: the agent's retry starts over."""
    agent_id = _seed_agent(session_per_request)
    job_id = _seed_job(session_per_request, agent_id, status="claimed")
    gate = Gate()
    released = []
    found_by_the_teardown = []
    db = MagicMock()

    def held_rollback():
        gate.hold()
        released.append(True)

    db.rollback = held_rollback
    scope = CancelScope()

    async def request():
        with scope:
            try:
                await agents.start_job(
                    job_id,
                    AgentJobStartRequest(),
                    current_agent=SimpleNamespace(id=agent_id),
                    db=db,
                )
            finally:
                found_by_the_teardown.extend(released or [False])

    running = asyncio.ensure_future(request())
    assert await asyncio.to_thread(gate.reached.wait, HOLD_SECONDS)
    if cancelled_by == "the task":
        running.cancel()
    else:
        scope.cancel()
    # Turns of the loop, in which a request that does not wait would end.
    for _ in range(10):
        await asyncio.sleep(0)
    gate.open()
    if cancelled_by == "the task":
        with pytest.raises(asyncio.CancelledError):
            await running
    else:
        await running

    assert found_by_the_teardown == [True]
    with session_per_request() as check:
        assert check.get(AgentJob, job_id).status == "claimed"


@pytest.mark.unit
def test_the_start_notification_looks_up_the_backup_off_the_loop(
    test_client, session_per_request, monkeypatch
):
    agent_id = _seed_agent(session_per_request)
    operation_id, job_id = _seed_backup_job(
        session_per_request, agent_id, status="claimed"
    )
    original = agents._get_linked_backup_job
    lookups_on_the_loop = []

    def recorded_lookup(job, db):
        lookups_on_the_loop.append(_on_the_loop())
        return original(job, db)

    monkeypatch.setattr(agents, "_get_linked_backup_job", recorded_lookup)
    notify = AsyncMock()
    monkeypatch.setattr(agents, "notify_backup_job_started", notify)

    response = _post(test_client, _job_path(job_id, "start"), {})

    assert response.status_code == 200
    # One lookup records the report, the other prepares the notification.
    assert lookups_on_the_loop == [False, False]
    assert notify.await_args.args[2].id == operation_id


@pytest.mark.unit
async def test_a_first_backup_start_closes_its_sessions_off_the_loop(
    test_db, session_per_request, monkeypatch
):
    """Closing a session ends its read, which is a rollback on the database.
    The request's session used to be closed in a worker, with the dependency;
    the notification's has to be as well."""
    agent_id = _seed_agent(session_per_request)
    _, job_id = _seed_backup_job(session_per_request, agent_id, status="claimed")
    closes_on_the_loop = []

    class RecordedSession(Session):
        def close(self):
            closes_on_the_loop.append(_on_the_loop())
            super().close()

    sessions = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=test_db.get_bind(),
        class_=RecordedSession,
    )
    notify = AsyncMock()
    monkeypatch.setattr(agents, "notify_backup_job_started", notify)

    with patch("app.database.database.SessionLocal", sessions):
        await agents.start_job(
            job_id,
            AgentJobStartRequest(),
            current_agent=SimpleNamespace(id=agent_id),
            db=MagicMock(),
        )

    assert notify.await_count == 1
    # The report's worker and the notification.
    assert closes_on_the_loop == [False, False]


@pytest.mark.unit
async def test_notifications_holding_the_pool_do_not_wait_behind_its_waiters(
    test_db, session_per_request, monkeypatch
):
    """A backup's first start notifies with a session of its own, which holds
    a connection from its job read until it is closed, and sends, looks up and
    closes in asyncio's default threads. Had the report workers waited for
    connections in those threads, notifications holding the whole pool would
    wait for workers that wait for them, until the pool timeout."""
    agent_id = _seed_agent(session_per_request)
    job_ids = [
        _seed_backup_job(session_per_request, agent_id, status="claimed")[1]
        for _ in range(4)
    ]
    engine = create_engine(
        test_db.get_bind().url,
        poolclass=QueuePool,
        pool_size=2,
        max_overflow=0,
        pool_timeout=HOLD_SECONDS,
        connect_args={"check_same_thread": False},
    )
    sessions = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    holding = []
    first_two_holding = asyncio.Event()
    notifications_go_on = asyncio.Event()
    notify_started = agents._notify_agent_job_started

    async def held_notification(db, job):
        # The session has read the job: it holds its connection.
        holding.append(job.id)
        if len(holding) <= 2:
            if len(holding) == 2:
                first_two_holding.set()
            await notifications_go_on.wait()
        await notify_started(db, job)

    monkeypatch.setattr(agents, "_notify_agent_job_started", held_notification)
    sent = []

    async def notify(db, job, backup_job):
        # As the notification service sends: in asyncio's default threads.
        await asyncio.to_thread(sent.append, job.id)

    monkeypatch.setattr(agents, "notify_backup_job_started", notify)
    workers = []
    all_workers_running = threading.Event()
    record = agents._record_job_start

    def counted_record(*args):
        workers.append(args[0])
        if len(workers) == len(job_ids):
            all_workers_running.set()
        return record(*args)

    monkeypatch.setattr(agents, "_record_job_start", counted_record)

    def report(job_id):
        return asyncio.ensure_future(
            agents.start_job(
                job_id,
                AgentJobStartRequest(),
                current_agent=SimpleNamespace(id=agent_id),
                db=MagicMock(),
            )
        )

    loop = asyncio.get_running_loop()
    default_threads = ThreadPoolExecutor(max_workers=2)
    waits = ThreadPoolExecutor(max_workers=1)
    loop.set_default_executor(default_threads)
    try:
        with patch("app.database.database.SessionLocal", sessions):
            first = [report(job_id) for job_id in job_ids[:2]]
            # Two notifications hold both connections ...
            await asyncio.wait_for(first_two_holding.wait(), HOLD_SECONDS)
            later = [report(job_id) for job_id in job_ids[2:]]
            # ... while two workers take both default threads to wait for one.
            assert await loop.run_in_executor(
                waits, all_workers_running.wait, HOLD_SECONDS
            )
            notifications_go_on.set()
            responses = await asyncio.gather(*first, *later, return_exceptions=True)
            await asyncio.gather(*agents._REPORT_TASKS)
    finally:
        loop.set_default_executor(ThreadPoolExecutor())
        default_threads.shutdown(wait=False)
        waits.shutdown(wait=False)
        engine.dispose()

    assert [getattr(r, "status", r) for r in responses] == ["running"] * 4
    assert sorted(holding) == sorted(job_ids)
    assert sorted(sent) == sorted(job_ids)


@pytest.mark.unit
@pytest.mark.parametrize("report", ["start", "complete"])
async def test_a_report_waits_for_connections_in_report_threads(
    test_db, session_per_request, monkeypatch, report
):
    """A notification holding a connection sends in asyncio's default threads.
    What may wait for a connection, the report's worker and the notification's
    job read, waits in the report threads instead: as many as asyncio's
    default threads, so a burst of reports does not start a thread each."""
    agent_id = _seed_agent(session_per_request)
    _, job_id = _seed_backup_job(
        session_per_request,
        agent_id,
        status="claimed" if report == "start" else "running",
    )
    reads = []

    class RecordedSession(Session):
        def get(self, entity, *args, **kwargs):
            reads.append((entity.__name__, threading.current_thread().name))
            return super().get(entity, *args, **kwargs)

    sessions = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=test_db.get_bind(),
        class_=RecordedSession,
    )
    monkeypatch.setattr(agents, "notify_backup_job_started", AsyncMock())
    monkeypatch.setattr(agents, "notify_backup_job_finished", AsyncMock())
    loop = asyncio.get_running_loop()
    default_threads = ThreadPoolExecutor(thread_name_prefix="asyncio-default")
    loop.set_default_executor(default_threads)
    agent = SimpleNamespace(id=agent_id)
    try:
        with patch("app.database.database.SessionLocal", sessions):
            if report == "start":
                await agents.start_job(
                    job_id, AgentJobStartRequest(), current_agent=agent, db=MagicMock()
                )
            else:
                await agents.complete_job(
                    job_id,
                    agents.AgentJobCompleteRequest(**COMPLETION),
                    current_agent=agent,
                )
    finally:
        loop.set_default_executor(ThreadPoolExecutor())
        default_threads.shutdown(wait=False)

    # The worker's first read and the notification's: each checks a
    # connection out. The lookup after the job read uses the one it holds.
    first_reads = {entity: name for entity, name in reversed(reads)}
    assert first_reads["AgentMachine"].startswith("agent-report")
    assert first_reads["AgentJob"].startswith("agent-report")


@pytest.mark.unit
def test_a_recorded_start_is_answered_when_its_notification_fails(
    test_client, session_per_request, monkeypatch
):
    agent_id = _seed_agent(session_per_request)
    _, job_id = _seed_backup_job(session_per_request, agent_id, status="claimed")
    original = agents._get_linked_backup_job
    calls = []

    def lookup_fails_after_the_commit(job, db):
        calls.append(job.id)
        if len(calls) == 1:
            return original(job, db)
        raise RuntimeError("the lookup failed")

    monkeypatch.setattr(agents, "_get_linked_backup_job", lookup_fails_after_the_commit)
    notify = AsyncMock()
    monkeypatch.setattr(agents, "notify_backup_job_started", notify)

    response = _post(test_client, _job_path(job_id, "start"), {})

    assert response.status_code == 200
    assert response.json()["status"] == "running"
    assert len(calls) == 2
    notify.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.parametrize("report", ["start", "complete"])
def test_a_recorded_report_is_answered_when_its_notification_cannot_read_the_job(
    test_client, test_db, session_per_request, monkeypatch, report
):
    """The report is committed before the notification reads the job again
    with a session of its own: a failure there must not fail the request."""
    agent_id = _seed_agent(session_per_request)
    _, job_id = _seed_backup_job(
        session_per_request,
        agent_id,
        status="claimed" if report == "start" else "running",
    )

    class JobReadFails(Session):
        def get(self, entity, *args, **kwargs):
            if entity is AgentJob:
                raise RuntimeError("the job read failed")
            return super().get(entity, *args, **kwargs)

    sessions = sessionmaker(
        autocommit=False, autoflush=False, bind=test_db.get_bind(), class_=JobReadFails
    )
    started = AsyncMock()
    finished = AsyncMock()
    monkeypatch.setattr(agents, "notify_backup_job_started", started)
    monkeypatch.setattr(agents, "notify_backup_job_finished", finished)

    with patch("app.database.database.SessionLocal", sessions):
        response = _post(
            test_client,
            _job_path(job_id, report),
            {} if report == "start" else COMPLETION,
        )

    assert response.status_code == 200
    expected = "running" if report == "start" else "completed"
    assert response.json()["status"] == expected
    with session_per_request() as db:
        assert db.get(AgentJob, job_id).status == expected
    started.assert_not_awaited()
    finished.assert_not_awaited()


@pytest.mark.unit
def test_a_start_report_keeps_its_refusals(test_client, session_per_request):
    agent_id = _seed_agent(session_per_request)
    final_job = _seed_job(session_per_request, agent_id, status="completed")
    unknown_status_job = _seed_job(session_per_request, agent_id, status="paused")

    final = _post(test_client, _job_path(final_job, "start"), {})
    not_startable = _post(test_client, _job_path(unknown_status_job, "start"), {})
    unknown = _post(test_client, _job_path(unknown_status_job + 1, "start"), {})

    assert final.status_code == 409
    assert final.json()["detail"]["key"] == "backend.errors.agents.jobAlreadyFinished"
    assert not_startable.status_code == 409
    assert (
        not_startable.json()["detail"]["key"] == "backend.errors.agents.jobNotStartable"
    )
    assert unknown.status_code == 404


@pytest.mark.unit
def test_a_heartbeat_authenticated_before_an_unregister_is_refused(
    test_client, database, monkeypatch
):
    agent_id = _seed_agent(database)
    gate = Gate()
    original = agents.mark_agent_online

    def held_mark(*args, **kwargs):
        gate.hold()
        return original(*args, **kwargs)

    monkeypatch.setattr(agents, "mark_agent_online", held_mark)

    beat, unregister = _while_held(
        gate,
        lambda: _post(test_client, "/api/agents/heartbeat", {"agent_id": AGENT_ID}),
        lambda: _post(test_client, "/api/agents/unregister"),
    )

    assert unregister.status_code == 204
    assert beat.status_code == 403
    with database() as db:
        assert db.get(AgentMachine, agent_id).status == "revoked"


@pytest.mark.unit
@pytest.mark.parametrize("status", ["running", "cancel_requested"])
def test_a_requeue_leaves_a_job_that_reported_after_its_read(
    test_client, database, monkeypatch, status
):
    """A report moves `updated_at` and not the status, so the status guard
    alone would requeue, or close as cancelled, a job that has just shown it
    is alive. A cancel request stays, so the agent is still told to stop."""
    agent_id = _seed_agent(database)
    job_id = _seed_idle_job(database, agent_id, status=status)
    original = agents._job_activity_at

    def report_lands(job):
        activity = original(job)
        _set_columns(database, AgentJob, job_id, {"updated_at": utc_now()})
        return activity

    monkeypatch.setattr(agents, "_job_activity_at", report_lands)

    with database() as db:
        agents._requeue_stale_agent_jobs(
            db,
            db.get(AgentMachine, agent_id),
            now=datetime.now(timezone.utc),
            running_job_ids=[],
        )
        db.commit()

    with database() as db:
        job = db.get(AgentJob, job_id)
        assert job.status == status
        assert job.started_at is not None


@pytest.mark.unit
@pytest.mark.skipif(not POSTGRES_URL, reason="BORG_TEST_POSTGRES_URL is not set")
@pytest.mark.parametrize("database", ["postgresql"], indirect=True)
def test_a_heartbeat_leaves_a_job_that_reports_during_it(
    test_client, database, monkeypatch
):
    """The same with real requests. PostgreSQL only: on SQLite the heartbeat
    holds the write lock from its first write, so no report gets in."""
    agent_id = _seed_agent(database)
    job_id = _seed_idle_job(database, agent_id)
    gate = Gate()
    _hold_after(monkeypatch, "_job_activity_at", gate)

    beat, report = _while_held(
        gate,
        lambda: _post(test_client, "/api/agents/heartbeat", {"agent_id": AGENT_ID}),
        lambda: _post(test_client, _job_path(job_id, "progress"), PROGRESS),
    )

    assert report.status_code == 200
    assert beat.status_code == 200
    with database() as db:
        job = db.get(AgentJob, job_id)
        assert job.status == "running"
        assert job.started_at is not None
        assert job.nfiles == PROGRESS["nfiles"]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("status", "settled_as"),
    [("running", "queued"), ("cancel_requested", "canceled")],
)
def test_a_heartbeat_still_settles_an_idle_job(
    test_client, database, status, settled_as
):
    job_id = _seed_idle_job(database, _seed_agent(database), status=status)

    beat = _post(test_client, "/api/agents/heartbeat", {"agent_id": AGENT_ID})

    assert beat.status_code == 200
    with database() as db:
        assert db.get(AgentJob, job_id).status == settled_as


@pytest.mark.unit
def test_rest_progress_refuses_a_percentage_it_cannot_store(
    test_client, session_per_request
):
    """The session path drops such a field; REST keeps refusing the report."""
    job_id = _seed_job(
        session_per_request, _seed_agent(session_per_request), status="running"
    )

    response = test_client.post(
        _job_path(job_id, "progress"),
        content=b'{"progress_percent": Infinity}',
        headers={
            "Content-Type": "application/json",
            "X-Borg-Agent-Authorization": f"Bearer {RAW_TOKEN}",
        },
    )

    assert response.status_code == 422
    with session_per_request() as db:
        assert db.get(AgentJob, job_id).progress is None


@pytest.mark.unit
def test_rest_progress_on_a_final_job_is_refused(test_client, session_per_request):
    job_id = _seed_job(
        session_per_request, _seed_agent(session_per_request), status="completed"
    )

    response = _post(test_client, _job_path(job_id, "progress"), PROGRESS)

    assert response.status_code == 409
    assert (
        response.json()["detail"]["key"] == "backend.errors.agents.jobAlreadyFinished"
    )
    with session_per_request() as db:
        assert db.get(AgentJob, job_id).progress is None


@pytest.mark.unit
def test_a_rest_keepalive_keeps_the_last_snapshot(test_client, session_per_request):
    job_id = _seed_job(
        session_per_request, _seed_agent(session_per_request), status="running"
    )

    report = _post(test_client, _job_path(job_id, "progress"), PROGRESS)
    keepalive = _post(test_client, _job_path(job_id, "progress"), {})

    assert report.json() == {"id": job_id, "status": "running"}
    assert keepalive.json() == {"id": job_id, "status": "running"}
    with session_per_request() as db:
        job = db.get(AgentJob, job_id)
        assert job.progress == PROGRESS
        assert job.nfiles == PROGRESS["nfiles"]


@pytest.mark.unit
@pytest.mark.parametrize(
    "endpoint", ["register", "heartbeat", "unregister", "claim", "progress"]
)
def test_an_endpoint_gives_its_connection_back_before_the_response(
    test_client, database, monkeypatch, endpoint
):
    """Each of these reads again after its commit. FastAPI validates the
    response of a plain `def` handler in another shared worker thread, before
    the request's session is closed: a session still holding its connection
    there waits for a thread while holding it."""
    import fastapi.routing
    from app.main import app

    agent_id = _seed_agent(database)
    job_id = _seed_job(
        database, agent_id, status="queued" if endpoint == "claim" else "running"
    )
    _seed_enrollment_token(database)
    monkeypatch.setattr("app.api.agents.verify_password", lambda token, hashed: True)
    request_session = app.dependency_overrides[get_db]
    sessions: list = []

    def recorded_session():
        requests = request_session()
        db = next(requests)
        sessions.append(db)
        try:
            yield db
        finally:
            requests.close()

    app.dependency_overrides[get_db] = recorded_session
    serialize = fastapi.routing.serialize_response
    holding_at_validation: list = []

    async def recording_serialize(*args, **kwargs):
        holding_at_validation.append(sessions[-1].in_transaction())
        return await serialize(*args, **kwargs)

    monkeypatch.setattr(fastapi.routing, "serialize_response", recording_serialize)

    if endpoint == "register":
        response = _register(test_client, "second laptop")
    elif endpoint == "heartbeat":
        response = _post(
            test_client,
            "/api/agents/heartbeat",
            {"agent_id": AGENT_ID, "running_job_ids": [job_id]},
        )
    elif endpoint == "unregister":
        response = _post(test_client, "/api/agents/unregister")
    else:
        body = PROGRESS if endpoint == "progress" else None
        response = _post(test_client, _job_path(job_id, endpoint), body)

    assert response.status_code in (200, 204)
    assert holding_at_validation == [False]
