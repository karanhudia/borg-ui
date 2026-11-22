"""Who may be handed an agent's job, take a claim back, or speak for it.

The dispatcher claims a queued job and sends it over the agent's session.
Three things went wrong around that (#1569):

- the claim asked only whether the job was queued, so a job claimed after its
  agent was revoked still went to the session the agent had left open;
- a failed send put the job back on the queue whenever it read `claimed`,
  also when the claim was a newer session's;
- a heartbeat of a session its successor had replaced marked the agent
  online, with no session registered once the successor was gone.

The tests run on SQLite and, with BORG_TEST_POSTGRES_URL set, on PostgreSQL.
"""

import asyncio
import os
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker

from app.api.agents import AgentSessionRevoked, _handle_agent_session_message
from app.database.database import Base, register_utc_session_timezone
from app.database.models import AgentJob, AgentMachine
from app.services import agent_job_dispatcher
from app.services.agent_connection_manager import (
    AgentConnection,
    agent_connection_manager,
)

POSTGRES_URL = os.getenv("BORG_TEST_POSTGRES_URL")
AGENT_ID = "agt_claims"
INACTIVE = ["revoked", "disabled", "deleted"]


@contextmanager
def _postgres_engine():
    """A schema of its own: the other PostgreSQL tests drop `public`."""
    schema = f"agent_claims_{uuid.uuid4().hex}"
    admin = create_engine(POSTGRES_URL)
    with admin.begin() as conn:
        conn.execute(text(f"CREATE SCHEMA {schema}"))
    engine = create_engine(
        POSTGRES_URL, connect_args={"options": f"-c search_path={schema}"}
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
def sessions(request, test_db):
    """Sessions on the database under test: one for the dispatch, others for
    what happens to the rows meanwhile."""
    if request.param == "sqlite":
        yield sessionmaker(autocommit=False, autoflush=False, bind=test_db.get_bind())
        return
    with _postgres_engine() as engine:
        yield sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture
def db(sessions):
    """The dispatching caller's session."""
    session = sessions()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def send(monkeypatch):
    """The agent has a session; what is sent to it is recorded."""
    send = AsyncMock()
    monkeypatch.setattr(agent_connection_manager, "is_connected", lambda _id: True)
    monkeypatch.setattr(agent_connection_manager, "send_command", send)
    return send


def _seed_agent(sessions, *, status: str = "online") -> int:
    with sessions() as db:
        agent = AgentMachine(
            name="Claims Agent",
            agent_id=AGENT_ID,
            token_hash="not checked here",
            token_prefix="claims",
            status=status,
            capabilities=[],
        )
        db.add(agent)
        db.commit()
        return agent.id


def _seed_queued_job(sessions, agent_id: int) -> int:
    with sessions() as db:
        job = AgentJob(
            agent_machine_id=agent_id,
            job_type="repository",
            status="queued",
            payload={"job_kind": "repository.delete_archive"},
        )
        db.add(job)
        db.commit()
        return job.id


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


class _Socket:
    """The agent's end of a session: the frames written to it."""

    def __init__(self) -> None:
        self.frames: list[dict] = []

    async def send_json(self, frame: dict) -> None:
        self.frames.append(frame)


def _connection(agent_id: int) -> AgentConnection:
    return AgentConnection(
        agent_machine_id=agent_id, agent_id=AGENT_ID, websocket=_Socket()
    )


@pytest.fixture
def registered():
    """Registers a connection as its agent's current session."""
    added = []

    def register(connection: AgentConnection) -> AgentConnection:
        agent_connection_manager._connections[connection.agent_machine_id] = connection
        added.append(connection.agent_machine_id)
        return connection

    yield register
    for agent_machine_id in added:
        agent_connection_manager._connections.pop(agent_machine_id, None)


# --- the claim needs an active agent -----------------------------------


@pytest.mark.unit
@pytest.mark.parametrize("inactive", INACTIVE)
async def test_a_job_is_not_claimed_for_an_agent_that_left(
    sessions, db, send, inactive
):
    """The agent's session is still open (it only notices at its next
    message), and the caller read the job while the agent was active."""
    agent_id = _seed_agent(sessions)
    job_id = _seed_queued_job(sessions, agent_id)
    job = db.get(AgentJob, job_id)
    assert job.status == "queued"
    untouched = job.updated_at
    _set_columns(sessions, AgentMachine, agent_id, {"status": inactive})

    sent = await agent_job_dispatcher.dispatch_agent_job_if_connected(db, job)

    assert sent is False
    send.assert_not_awaited()
    stored = _row(sessions, AgentJob, job_id)
    assert stored.status == "queued"
    assert stored.claimed_at is None
    # Never claimed, not claimed and given back.
    assert stored.updated_at == untouched


@pytest.mark.unit
async def test_a_job_claimed_before_a_revocation_is_not_sent_after_it(
    sessions, db, registered
):
    """The claim and the send are two steps: a revocation committed between
    them wins, and the job is back on the queue."""
    agent_id = _seed_agent(sessions)
    job_id = _seed_queued_job(sessions, agent_id)
    connection = registered(_connection(agent_id))
    job = db.get(AgentJob, job_id)
    revoked = []

    @event.listens_for(db, "after_commit")
    def revoke_once_claimed(_session):
        if not revoked and _row(sessions, AgentJob, job_id).status == "claimed":
            revoked.append(True)
            _set_columns(sessions, AgentMachine, agent_id, {"status": "revoked"})

    sent = await agent_job_dispatcher.dispatch_agent_job_if_connected(db, job)

    assert revoked, "the job was never claimed"
    assert sent is False
    assert connection.websocket.frames == []
    stored = _row(sessions, AgentJob, job_id)
    assert stored.status == "queued"
    assert stored.claimed_at is None


@pytest.mark.unit
@pytest.mark.parametrize("inactive", INACTIVE)
async def test_a_revocation_while_the_send_waits_for_the_session_wins(
    sessions, db, registered, inactive
):
    """A session writes one frame at a time, and a client that reads slowly
    keeps the next one waiting. The agent is asked about again when the
    job's frame is next to go out, not only when the wait began."""
    agent_id = _seed_agent(sessions)
    job_id = _seed_queued_job(sessions, agent_id)
    connection = registered(_connection(agent_id))
    job = db.get(AgentJob, job_id)

    await connection.send_lock.acquire()  # another frame is going out
    try:
        dispatch = asyncio.ensure_future(
            agent_job_dispatcher.dispatch_agent_job_if_connected(db, job)
        )
        # Up to its first wait: the session's send lock.
        await asyncio.sleep(0)
        claimed_while_waiting = _row(sessions, AgentJob, job_id).status
        _set_columns(sessions, AgentMachine, agent_id, {"status": inactive})
    finally:
        connection.send_lock.release()
    sent = await dispatch

    assert claimed_while_waiting == "claimed"
    assert sent is False
    assert connection.websocket.frames == []
    stored = _row(sessions, AgentJob, job_id)
    assert stored.status == "queued"
    assert stored.claimed_at is None


@pytest.mark.unit
async def test_a_job_that_waited_for_the_session_reaches_an_active_agent(
    sessions, db, registered
):
    agent_id = _seed_agent(sessions)
    job_id = _seed_queued_job(sessions, agent_id)
    connection = registered(_connection(agent_id))
    job = db.get(AgentJob, job_id)

    await connection.send_lock.acquire()
    try:
        dispatch = asyncio.ensure_future(
            agent_job_dispatcher.dispatch_agent_job_if_connected(db, job)
        )
        await asyncio.sleep(0)
    finally:
        connection.send_lock.release()
    sent = await dispatch

    assert sent is True
    stored = _row(sessions, AgentJob, job_id)
    assert stored.status == "claimed"
    assert [frame["job_id"] for frame in connection.websocket.frames] == [job_id]
    assert connection.websocket.frames[0]["attempt"] == (
        agent_job_dispatcher.agent_job_attempt(stored)
    )


@pytest.mark.unit
async def test_an_active_agents_job_is_claimed_and_sent(sessions, db, send):
    agent_id = _seed_agent(sessions)
    job_id = _seed_queued_job(sessions, agent_id)
    job = db.get(AgentJob, job_id)

    sent = await agent_job_dispatcher.dispatch_agent_job_if_connected(db, job)

    assert sent is True
    send.assert_awaited_once()
    stored = _row(sessions, AgentJob, job_id)
    assert stored.status == "claimed"
    assert send.await_args.kwargs["attempt"] == (
        agent_job_dispatcher.agent_job_attempt(stored)
    )


# --- a failed send takes back its own claim only -------------------------


@pytest.mark.unit
async def test_a_failed_send_takes_its_own_claim_back(sessions, db, send):
    agent_id = _seed_agent(sessions)
    job_id = _seed_queued_job(sessions, agent_id)
    job = db.get(AgentJob, job_id)
    send.side_effect = RuntimeError("socket closed")

    sent = await agent_job_dispatcher.dispatch_agent_job_if_connected(db, job)

    assert sent is False
    stored = _row(sessions, AgentJob, job_id)
    assert stored.status == "queued"
    assert stored.claimed_at is None


@pytest.mark.unit
async def test_a_failed_send_leaves_a_newer_claim_alone(sessions, db, send):
    """While the send waits on a session that is going away, the agent's new
    session puts the undelivered job back on the queue and claims it. The old
    send's failure is not about that claim."""
    agent_id = _seed_agent(sessions)
    job_id = _seed_queued_job(sessions, agent_id)
    job = db.get(AgentJob, job_id)
    newer_claim = datetime.now(timezone.utc) + timedelta(seconds=5)

    async def replaced_while_sending(*args, **kwargs):
        _set_columns(
            sessions, AgentJob, job_id, {"status": "queued", "claimed_at": None}
        )
        _set_columns(
            sessions,
            AgentJob,
            job_id,
            {"status": "claimed", "claimed_at": newer_claim},
        )
        raise RuntimeError("session was replaced")

    send.side_effect = replaced_while_sending

    sent = await agent_job_dispatcher.dispatch_agent_job_if_connected(db, job)

    assert sent is False
    stored = _row(sessions, AgentJob, job_id)
    assert stored.status == "claimed"
    assert agent_job_dispatcher.agent_job_attempt(stored) == (
        newer_claim - datetime(1970, 1, 1, tzinfo=timezone.utc)
    ) // timedelta(microseconds=1)


# --- only the agent's current session marks it online --------------------


@pytest.mark.unit
async def test_the_current_sessions_heartbeat_marks_the_agent_online(
    sessions, db, registered
):
    agent_id = _seed_agent(sessions, status="offline")
    connection = registered(_connection(agent_id))

    await _handle_agent_session_message(
        db, agent_id, {"type": "heartbeat"}, connection=connection, check_active=True
    )

    stored = _row(sessions, AgentMachine, agent_id)
    assert stored.status == "online"
    assert stored.last_seen_at is not None


@pytest.mark.unit
async def test_a_replaced_sessions_heartbeat_does_not_mark_the_agent_online(
    sessions, db
):
    """Its successor has come and gone, and marked the agent offline on its
    way out: a heartbeat the replaced session still had buffered is not a
    sign of life from the agent's session."""
    agent_id = _seed_agent(sessions, status="offline")
    replaced = _connection(agent_id)
    assert agent_connection_manager.get(agent_id) is None

    await _handle_agent_session_message(
        db, agent_id, {"type": "heartbeat"}, connection=replaced, check_active=True
    )

    stored = _row(sessions, AgentMachine, agent_id)
    assert stored.status == "offline"
    assert stored.last_seen_at is None


@pytest.mark.unit
async def test_a_replaced_sessions_heartbeat_leaves_its_successor_to_speak(
    sessions, db, registered
):
    agent_id = _seed_agent(sessions, status="online")
    replaced = _connection(agent_id)
    registered(_connection(agent_id))

    await _handle_agent_session_message(
        db, agent_id, {"type": "heartbeat"}, connection=replaced, check_active=True
    )

    stored = _row(sessions, AgentMachine, agent_id)
    assert stored.status == "online"
    assert stored.last_seen_at is None


@pytest.mark.unit
@pytest.mark.parametrize("inactive", INACTIVE)
async def test_a_replaced_sessions_heartbeat_is_refused_once_the_agent_left(
    sessions, db, inactive
):
    """The heartbeat's own check, as before: it does not lean on the
    session's check of every message."""
    agent_id = _seed_agent(sessions, status=inactive)

    with pytest.raises(AgentSessionRevoked):
        await _handle_agent_session_message(
            db,
            agent_id,
            {"type": "heartbeat"},
            connection=_connection(agent_id),
            check_active=False,
        )

    assert _row(sessions, AgentMachine, agent_id).status == inactive
