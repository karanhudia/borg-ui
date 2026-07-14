"""Idle agents stay live server-side.

An agent keeps its WebSocket alive with protocol-level pings, but those never
reach application code, so `last_seen_at` used to only advance while a job was
running (via POST /heartbeat). An idle-but-healthy agent therefore looked
stale. The agent now sends an application-level `heartbeat` message on its idle
timer; the session handler must refresh `last_seen_at` (and mark the agent
online) when it arrives.
"""

import pytest

from app.api.agents import _handle_agent_session_message
from app.core.security import get_password_hash
from app.database.models import AgentMachine


def _create_agent(test_db, *, status="offline"):
    agent = AgentMachine(
        name="HB Agent",
        agent_id="agt_hb",
        token_hash=get_password_hash("secret"),
        token_prefix="secret"[:20],
        status=status,
        last_seen_at=None,
        capabilities=[],
    )
    test_db.add(agent)
    test_db.commit()
    test_db.refresh(agent)
    return agent


@pytest.mark.unit
@pytest.mark.asyncio
async def test_heartbeat_message_refreshes_last_seen(test_db):
    agent = _create_agent(test_db, status="offline")
    assert agent.last_seen_at is None

    await _handle_agent_session_message(test_db, agent.id, {"type": "heartbeat"})

    test_db.refresh(agent)
    assert agent.last_seen_at is not None
    assert agent.status == "online"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_non_heartbeat_message_does_not_require_a_job(test_db):
    # A heartbeat carries no job_id; the early return must not touch job state.
    agent = _create_agent(test_db)
    # Should not raise even though there is no matching agent job.
    await _handle_agent_session_message(test_db, agent.id, {"type": "heartbeat"})
    test_db.refresh(agent)
    assert agent.status == "online"
