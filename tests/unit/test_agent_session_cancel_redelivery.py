"""A cancel the session agent did not get is sent again.

The server sends a job's cancel command once, over the session open at that
moment. While the session is down nothing is sent, and the job stays
`cancel_requested` while the reconnected agent keeps running it: its hello
and heartbeats list the job, so neither the requeue pass nor the reaper
settles it (#1443). The REST heartbeat of a polling agent answers with the
`cancel_requested` jobs among its running ones; a session heartbeat now sends
their cancel command the same way. The hello's counterpart is covered with
the other hello tests in test_api_agents.py.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from app.api import agents as agents_api
from app.api.agents import _handle_agent_session_message
from app.core.security import get_password_hash
from app.database.models import AgentJob, AgentMachine
from app.services import agent_job_dispatcher
from app.services.agent_connection_manager import (
    AgentConnection,
    AgentConnectionManager,
)


def _agent(db, *, agent_id="agt_cancel") -> AgentMachine:
    agent = AgentMachine(
        name=f"Agent {agent_id}",
        agent_id=agent_id,
        token_hash=get_password_hash("secret"),
        token_prefix="secret",
        status="online",
        capabilities=[],
    )
    db.add(agent)
    db.commit()
    db.refresh(agent)
    return agent


def _job(db, agent, *, status) -> AgentJob:
    started_at = datetime.now(timezone.utc) - timedelta(minutes=10)
    job = AgentJob(
        agent_machine_id=agent.id,
        job_type="repository",
        status=status,
        payload={"job_kind": "repository.check"},
        claimed_at=started_at,
        started_at=started_at,
        created_at=started_at,
        updated_at=started_at,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def _registered(monkeypatch, agent) -> AgentConnection:
    """The agent's current session, seen by the session handler and by the
    dispatcher that sends the cancel."""
    manager = AgentConnectionManager()
    connection = AgentConnection(
        agent_machine_id=agent.id, agent_id=agent.agent_id, websocket=AsyncMock()
    )
    manager._connections[agent.id] = connection
    monkeypatch.setattr(agents_api, "agent_connection_manager", manager)
    monkeypatch.setattr(agent_job_dispatcher, "agent_connection_manager", manager)
    return connection


def _cancelled_job_ids(connection: AgentConnection) -> list[int]:
    return [
        call.args[0]["job_id"]
        for call in connection.websocket.send_json.await_args_list
        if call.args[0].get("command") == "cancel"
    ]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_session_heartbeat_sends_the_cancel_of_a_listed_job_again(
    test_db, monkeypatch
):
    agent = _agent(test_db)
    connection = _registered(monkeypatch, agent)
    owed = _job(test_db, agent, status="cancel_requested")
    running = _job(test_db, agent, status="running")

    await _handle_agent_session_message(
        test_db,
        agent.id,
        {"type": "heartbeat", "running_job_ids": [owed.id, running.id]},
        connection=connection,
    )

    assert _cancelled_job_ids(connection) == [owed.id]
    frame = connection.websocket.send_json.await_args_list[0].args[0]
    assert frame["type"] == "command"
    assert frame["payload"] == {"job_id": owed.id}
    # The agent settles the job once its worker stops; until then it stays
    # with the agent, and the next heartbeat asks again.
    test_db.refresh(owed)
    assert owed.status == "cancel_requested"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_session_heartbeat_sends_no_cancel_for_a_job_it_does_not_list(
    test_db, monkeypatch
):
    """A job the agent does not run is the requeue pass's to settle; this
    agent is not asked to stop another agent's job either."""
    agent = _agent(test_db)
    connection = _registered(monkeypatch, agent)
    _job(test_db, agent, status="cancel_requested")
    other_agents_job = _job(
        test_db, _agent(test_db, agent_id="agt_other"), status="cancel_requested"
    )

    await _handle_agent_session_message(
        test_db,
        agent.id,
        {"type": "heartbeat", "running_job_ids": [other_agents_job.id]},
        connection=connection,
    )

    assert _cancelled_job_ids(connection) == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_heartbeat_of_a_replaced_session_sends_no_cancel(test_db, monkeypatch):
    """A list speaks for its own process only, as for the requeue pass."""
    agent = _agent(test_db)
    current = _registered(monkeypatch, agent)
    replaced = AgentConnection(
        agent_machine_id=agent.id, agent_id=agent.agent_id, websocket=AsyncMock()
    )
    owed = _job(test_db, agent, status="cancel_requested")

    await _handle_agent_session_message(
        test_db,
        agent.id,
        {"type": "heartbeat", "running_job_ids": [owed.id]},
        connection=replaced,
    )

    assert _cancelled_job_ids(current) == []
    assert _cancelled_job_ids(replaced) == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_heartbeat_stops_sending_cancels_once_its_session_is_replaced(
    test_db, monkeypatch
):
    """A newer session that takes over while the pass sends does not get
    the rest of the old session's cancels."""
    agent = _agent(test_db)
    connection = _registered(monkeypatch, agent)
    successor = AgentConnection(
        agent_machine_id=agent.id, agent_id=agent.agent_id, websocket=AsyncMock()
    )
    first = _job(test_db, agent, status="cancel_requested")
    second = _job(test_db, agent, status="cancel_requested")

    async def replace_on_first_cancel(frame):
        if frame.get("command") == "cancel":
            agents_api.agent_connection_manager._connections[agent.id] = successor

    connection.websocket.send_json.side_effect = replace_on_first_cancel

    await _handle_agent_session_message(
        test_db,
        agent.id,
        {"type": "heartbeat", "running_job_ids": [first.id, second.id]},
        connection=connection,
    )

    assert _cancelled_job_ids(connection) == [first.id]
    assert _cancelled_job_ids(successor) == []
