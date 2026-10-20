"""A job's attempt, and what a session heartbeat's running list settles.

The agent numbers every run's log lines from 0, and the server keys a line by
(agent_job_id, sequence) alone, so a line of a run that stopped could be
stored as the retry's and push the retry's own line out as a duplicate
(#1383). The server now tells the agent which attempt it is running (the
job's claim time, which a requeue resets), the agent sends it with every log
line on both transports, and the server drops a line of any other attempt.

A session heartbeat from agent 0.1.21 on lists the jobs its process runs
(#1377): it settles a job the process no longer runs the way the REST
heartbeat of a polling agent does, without waiting for the reaper.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from app.api import agents as agents_api
from app.api.agents import (
    STALE_AGENT_JOB_REQUEUE_AFTER,
    AgentJobLogRequest,
    _handle_agent_session_message,
    upload_job_log,
)
from app.core.security import get_password_hash
from app.database.models import AgentJob, AgentJobLog, AgentMachine
from app.services import agent_job_dispatcher
from app.services.agent_connection_manager import (
    AgentConnection,
    AgentConnectionManager,
)

EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def _attempt(claimed_at: datetime) -> int:
    """The attempt the server hands out: the claim time in whole microseconds
    since the epoch."""
    if claimed_at.tzinfo is None:
        claimed_at = claimed_at.replace(tzinfo=timezone.utc)
    return (claimed_at - EPOCH) // timedelta(microseconds=1)


def _agent(db) -> AgentMachine:
    agent = AgentMachine(
        name="Attempt Agent",
        agent_id="agt_attempt",
        token_hash=get_password_hash("secret"),
        token_prefix="secret",
        status="online",
        capabilities=[],
    )
    db.add(agent)
    db.commit()
    db.refresh(agent)
    return agent


def _job(db, agent, *, status="running", claimed_at=None, age=timedelta(0)):
    now = datetime.now(timezone.utc)
    claimed_at = claimed_at if claimed_at is not None else now - age
    job = AgentJob(
        agent_machine_id=agent.id,
        job_type="repository",
        status=status,
        payload={"job_kind": "repository.check"},
        claimed_at=None if status == "queued" else claimed_at,
        started_at=claimed_at if status in ("running", "cancel_requested") else None,
        created_at=claimed_at,
        updated_at=claimed_at,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def _claim_again(db, job, *, at):
    """What a requeue followed by the next dispatch leaves: a new claim."""
    job.status = "claimed"
    job.claimed_at = at
    job.started_at = None
    db.commit()
    db.refresh(job)


def _lines(db, job):
    return [
        (row.sequence, row.message)
        for row in db.query(AgentJobLog)
        .filter(AgentJobLog.agent_job_id == job.id)
        .order_by(AgentJobLog.sequence.asc())
    ]


@pytest.mark.unit
def test_rest_log_line_of_an_earlier_attempt_is_dropped_and_acknowledged(test_db):
    agent = _agent(test_db)
    first_claim = datetime.now(timezone.utc) - timedelta(minutes=5)
    job = _job(test_db, agent, claimed_at=first_claim)
    first_attempt = _attempt(first_claim)
    _claim_again(test_db, job, at=datetime.now(timezone.utc))

    response = upload_job_log(
        job.id,
        AgentJobLogRequest(sequence=0, message="first run", attempt=first_attempt),
        agent,
        test_db,
    )

    assert response.accepted is True
    assert response.superseded is True
    assert _lines(test_db, job) == []

    # The retry's own line with that sequence is stored, not a duplicate.
    retry = upload_job_log(
        job.id,
        AgentJobLogRequest(
            sequence=0, message="retry", attempt=_attempt(job.claimed_at)
        ),
        agent,
        test_db,
    )
    assert retry.duplicate is False
    assert _lines(test_db, job) == [(0, "retry")]


@pytest.mark.unit
def test_rest_log_line_for_a_job_back_on_the_queue_is_dropped(test_db):
    """A requeue clears the claim: no attempt runs, so no line belongs."""
    agent = _agent(test_db)
    first_claim = datetime.now(timezone.utc) - timedelta(minutes=5)
    job = _job(test_db, agent, claimed_at=first_claim)
    job.status = "queued"
    job.claimed_at = None
    job.started_at = None
    test_db.commit()

    response = upload_job_log(
        job.id,
        AgentJobLogRequest(
            sequence=3, message="first run", attempt=_attempt(first_claim)
        ),
        agent,
        test_db,
    )

    assert response.superseded is True
    assert _lines(test_db, job) == []


@pytest.mark.unit
def test_rest_log_line_without_an_attempt_is_stored_as_before(test_db):
    """Agents before 0.1.21 send no attempt: their lines keep today's path,
    and the response keeps today's shape."""
    agent = _agent(test_db)
    job = _job(test_db, agent)

    response = upload_job_log(
        job.id, AgentJobLogRequest(sequence=0, message="old agent"), agent, test_db
    )

    assert response.model_dump(exclude_none=True) == {
        "accepted": True,
        "duplicate": False,
    }
    assert _lines(test_db, job) == [(0, "old agent")]


@pytest.mark.unit
def test_rest_log_line_of_the_current_attempt_is_stored(test_db):
    agent = _agent(test_db)
    job = _job(test_db, agent)

    response = upload_job_log(
        job.id,
        AgentJobLogRequest(
            sequence=0, message="current", attempt=_attempt(job.claimed_at)
        ),
        agent,
        test_db,
    )

    assert response.duplicate is False
    assert not response.superseded
    assert _lines(test_db, job) == [(0, "current")]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_session_log_frame_of_an_earlier_attempt_is_dropped(test_db):
    agent = _agent(test_db)
    first_claim = datetime.now(timezone.utc) - timedelta(minutes=5)
    job = _job(test_db, agent, claimed_at=first_claim)
    _claim_again(test_db, job, at=datetime.now(timezone.utc))

    await _handle_agent_session_message(
        test_db,
        agent.id,
        {
            "type": "log",
            "job_id": job.id,
            "sequence": 0,
            "message": "first run",
            "attempt": _attempt(first_claim),
        },
    )
    await _handle_agent_session_message(
        test_db,
        agent.id,
        {
            "type": "log",
            "job_id": job.id,
            "sequence": 0,
            "message": "retry",
            "attempt": _attempt(job.claimed_at),
        },
    )
    await _handle_agent_session_message(
        test_db,
        agent.id,
        {"type": "log", "job_id": job.id, "sequence": 1, "message": "no attempt"},
    )

    assert _lines(test_db, job) == [(0, "retry"), (1, "no attempt")]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_dispatch_tells_the_agent_which_attempt_it_runs(test_db, monkeypatch):
    agent = _agent(test_db)
    job = _job(test_db, agent, status="queued")
    manager = AgentConnectionManager()
    websocket = AsyncMock()
    manager._connections[agent.id] = AgentConnection(
        agent_machine_id=agent.id, agent_id=agent.agent_id, websocket=websocket
    )
    monkeypatch.setattr(agent_job_dispatcher, "agent_connection_manager", manager)

    sent = await agent_job_dispatcher.dispatch_agent_job_if_connected(test_db, job)

    assert sent is True
    test_db.refresh(job)
    frame = websocket.send_json.await_args.args[0]
    assert frame["job_id"] == job.id
    assert frame["attempt"] == _attempt(job.claimed_at)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cancel_frame_carries_no_attempt(test_db, monkeypatch):
    """Only a job's own run has an attempt; other frames keep their shape."""
    agent = _agent(test_db)
    job = _job(test_db, agent)
    manager = AgentConnectionManager()
    websocket = AsyncMock()
    manager._connections[agent.id] = AgentConnection(
        agent_machine_id=agent.id, agent_id=agent.agent_id, websocket=websocket
    )
    monkeypatch.setattr(agent_job_dispatcher, "agent_connection_manager", manager)

    await agent_job_dispatcher.dispatch_agent_cancel_if_connected(job)

    frame = websocket.send_json.await_args.args[0]
    assert "attempt" not in frame


def _registered(monkeypatch, agent):
    manager = AgentConnectionManager()
    connection = AgentConnection(
        agent_machine_id=agent.id, agent_id=agent.agent_id, websocket=AsyncMock()
    )
    manager._connections[agent.id] = connection
    monkeypatch.setattr(agents_api, "agent_connection_manager", manager)
    return connection


STALE = STALE_AGENT_JOB_REQUEUE_AFTER + timedelta(seconds=30)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_session_heartbeat_requeues_a_started_job_its_process_no_longer_runs(
    test_db, monkeypatch
):
    agent = _agent(test_db)
    connection = _registered(monkeypatch, agent)
    gone = _job(test_db, agent, age=STALE)
    listed = _job(test_db, agent, age=STALE)
    fresh = _job(test_db, agent, age=timedelta(seconds=5))

    await _handle_agent_session_message(
        test_db,
        agent.id,
        {"type": "heartbeat", "running_job_ids": [listed.id]},
        connection=connection,
    )

    for job in (gone, listed, fresh):
        test_db.refresh(job)
    assert gone.status == "queued"
    assert gone.claimed_at is None
    assert listed.status == "running"
    # Inside the window, as on the REST heartbeat: a job just dispatched may
    # not be registered on the agent yet.
    assert fresh.status == "running"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_session_heartbeat_settles_a_cancel_its_process_no_longer_runs(
    test_db, monkeypatch
):
    agent = _agent(test_db)
    connection = _registered(monkeypatch, agent)
    job = _job(test_db, agent, status="cancel_requested", age=STALE)

    await _handle_agent_session_message(
        test_db,
        agent.id,
        {"type": "heartbeat", "running_job_ids": []},
        connection=connection,
    )

    test_db.refresh(job)
    assert job.status == "canceled"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_session_heartbeat_without_a_list_settles_nothing(test_db, monkeypatch):
    """Agents before 0.1.21 send a bare heartbeat: nothing changes for them."""
    agent = _agent(test_db)
    connection = _registered(monkeypatch, agent)
    job = _job(test_db, agent, age=STALE)

    await _handle_agent_session_message(
        test_db, agent.id, {"type": "heartbeat"}, connection=connection
    )

    test_db.refresh(job)
    assert job.status == "running"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_session_heartbeat_of_a_replaced_session_settles_nothing(
    test_db, monkeypatch
):
    """A list speaks for its own process only. A session the agent's newer
    connection replaced must not settle what the newer process runs."""
    agent = _agent(test_db)
    _registered(monkeypatch, agent)
    replaced = AgentConnection(
        agent_machine_id=agent.id, agent_id=agent.agent_id, websocket=AsyncMock()
    )
    job = _job(test_db, agent, age=STALE)

    await _handle_agent_session_message(
        test_db,
        agent.id,
        {"type": "heartbeat", "running_job_ids": []},
        connection=replaced,
    )

    test_db.refresh(job)
    assert job.status == "running"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_session_heartbeat_with_a_malformed_list_settles_nothing(
    test_db, monkeypatch
):
    agent = _agent(test_db)
    connection = _registered(monkeypatch, agent)
    job = _job(test_db, agent, age=STALE)

    for running in ("1,2", [str(job.id)], [True], None):
        await _handle_agent_session_message(
            test_db,
            agent.id,
            {"type": "heartbeat", "running_job_ids": running},
            connection=connection,
        )

    test_db.refresh(job)
    assert job.status == "running"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_a_job_on_the_heartbeat_list_is_not_reaped(test_db, monkeypatch):
    """The agent lists a job while it runs it silently or keeps an outcome
    whose report does not get through; the reaper must not fail it."""
    from app.services.agent_job_reaper import (
        AGENT_JOB_REAP_AFTER,
        reap_stale_agent_jobs,
    )

    agent = _agent(test_db)
    connection = _registered(monkeypatch, agent)
    listed = _job(test_db, agent, age=AGENT_JOB_REAP_AFTER + timedelta(minutes=1))
    other_agents_job = _job(
        test_db, _other_agent(test_db), age=AGENT_JOB_REAP_AFTER + timedelta(minutes=1)
    )

    await _handle_agent_session_message(
        test_db,
        agent.id,
        # A job of another agent on the list is not this agent's to vouch for.
        {"type": "heartbeat", "running_job_ids": [listed.id, other_agents_job.id]},
        connection=connection,
    )
    reap_stale_agent_jobs(test_db)

    test_db.refresh(listed)
    test_db.refresh(other_agents_job)
    assert listed.status == "running"
    assert other_agents_job.status == "failed"


def _other_agent(db) -> AgentMachine:
    agent = AgentMachine(
        name="Other Agent",
        agent_id="agt_other",
        token_hash=get_password_hash("secret"),
        token_prefix="secret",
        status="online",
        capabilities=[],
    )
    db.add(agent)
    db.commit()
    db.refresh(agent)
    return agent


@pytest.mark.unit
@pytest.mark.asyncio
async def test_a_dropped_session_log_line_ends_its_transaction(test_db):
    """The session would hold its pooled connection until the next message."""
    agent = _agent(test_db)
    first_claim = datetime.now(timezone.utc) - timedelta(minutes=5)
    job = _job(test_db, agent, claimed_at=first_claim)
    _claim_again(test_db, job, at=datetime.now(timezone.utc))
    test_db.commit()

    await _handle_agent_session_message(
        test_db,
        agent.id,
        {
            "type": "log",
            "job_id": job.id,
            "sequence": 0,
            "message": "first run",
            "attempt": _attempt(first_claim),
        },
    )

    assert not test_db.in_transaction()
