"""A queued agent job that missed its immediate dispatch is sent again by the
process that holds the agent's session, without waiting for a reconnect.

The miss (#1136): the job is created by a server process that holds no
session for the agent (a process in its graceful-shutdown window keeps
running the operations runner after its sessions were closed, while the
replacement process already serves the agent). The dispatcher there returns
without a send, a warning or a row write, and the serving process only ever
re-dispatched on session start, so the job stayed `queued` until the agent's
next reconnect and blocked its repository through admission meanwhile.
"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from app.database.models import AgentJob, AgentMachine
from app.services import agent_job_dispatcher
from app.services.agent_connection_manager import (
    AgentConnection,
    AgentConnectionManager,
)


def _agent(db, name: str = "redispatch-agent") -> AgentMachine:
    from app.core.security import get_password_hash

    agent = AgentMachine(
        name=name,
        agent_id=f"agt_{name}",
        token_hash=get_password_hash("secret"),
        token_prefix="secret",
        status="online",
        capabilities=[],
    )
    db.add(agent)
    db.commit()
    return agent


def _queued_job(db, agent: AgentMachine, *, age_seconds: float = 0.0) -> AgentJob:
    created = datetime.utcnow() - timedelta(seconds=age_seconds)
    job = AgentJob(
        agent_machine_id=agent.id,
        job_type="repository",
        status="queued",
        payload={"job_kind": "repository.list_archives"},
        created_at=created,
        updated_at=created,
    )
    db.add(job)
    db.commit()
    return job


def _session(manager: AgentConnectionManager, agent: AgentMachine):
    """A live session for `agent` in `manager`, with a recording socket."""
    websocket = AsyncMock()
    connection = AgentConnection(
        agent_machine_id=agent.id, agent_id=agent.agent_id, websocket=websocket
    )
    manager._connections[agent.id] = connection
    return websocket


@pytest.mark.unit
@pytest.mark.asyncio
async def test_a_process_without_the_session_leaves_the_job_untouched(
    test_db, monkeypatch
):
    """The creating process holds no session for the agent: no send, no
    warning, no row write. The job looks exactly like one nobody tried to
    send (only an info line says why it was left)."""
    agent = _agent(test_db)
    job = _queued_job(test_db, agent)
    monkeypatch.setattr(
        agent_job_dispatcher, "agent_connection_manager", AgentConnectionManager()
    )
    warnings: list = []
    monkeypatch.setattr(
        agent_job_dispatcher.logger, "warning", lambda *a, **k: warnings.append(k)
    )

    sent = await agent_job_dispatcher.dispatch_agent_job_best_effort(test_db, job)

    assert sent is False
    assert warnings == []
    test_db.expire_all()
    row = test_db.get(AgentJob, job.id)
    assert row.status == "queued"
    assert row.claimed_at is None
    assert row.updated_at == row.created_at


@pytest.mark.unit
@pytest.mark.asyncio
async def test_the_serving_process_redispatches_on_the_agents_heartbeat(
    test_db, monkeypatch
):
    """The process that holds the session sends a queued job it did not
    create once the agent's next heartbeat arrives, instead of waiting for
    the next reconnect."""
    from app.api import agents as agents_api

    agent = _agent(test_db)
    manager = AgentConnectionManager()
    websocket = _session(manager, agent)
    monkeypatch.setattr(agent_job_dispatcher, "agent_connection_manager", manager)
    monkeypatch.setattr(agents_api, "agent_connection_manager", manager)
    job = _queued_job(test_db, agent, age_seconds=60)

    await agents_api._handle_agent_session_message(
        test_db, agent.id, {"type": "heartbeat"}
    )

    test_db.expire_all()
    row = test_db.get(AgentJob, job.id)
    assert row.status == "claimed"
    assert row.claimed_at is not None
    websocket.send_json.assert_awaited_once()
    frame = websocket.send_json.await_args.args[0]
    assert frame["type"] == "command"
    assert frame["job_id"] == job.id
    assert frame["command"] == "repository.list_archives"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_the_heartbeat_leaves_a_fresh_job_to_its_creator(test_db, monkeypatch):
    """Inside the grace the creator's own dispatch is still on its way."""
    from app.api import agents as agents_api

    agent = _agent(test_db)
    manager = AgentConnectionManager()
    websocket = _session(manager, agent)
    monkeypatch.setattr(agent_job_dispatcher, "agent_connection_manager", manager)
    monkeypatch.setattr(agents_api, "agent_connection_manager", manager)
    job = _queued_job(test_db, agent, age_seconds=1)

    await agents_api._handle_agent_session_message(
        test_db, agent.id, {"type": "heartbeat"}
    )

    # The pass ended its read transaction: the idle session holds no
    # pooled connection until the next message.
    assert not test_db.in_transaction()
    test_db.expire_all()
    assert test_db.get(AgentJob, job.id).status == "queued"
    websocket.send_json.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["claimed", "running"])
async def test_a_job_another_pass_took_is_not_sent_again(test_db, monkeypatch, status):
    """Two passes can hold the same queued list (the heartbeat and a
    reconnect of the same agent). The first send's commit expires the other
    pass's copies, which then reload with what the sender wrote: a job that
    reads `claimed` (or `running`, once the agent started it) has been sent
    and must not go out a second time."""
    from sqlalchemy.orm import sessionmaker

    agent = _agent(test_db)
    manager = AgentConnectionManager()
    websocket = _session(manager, agent)
    monkeypatch.setattr(agent_job_dispatcher, "agent_connection_manager", manager)
    job = _queued_job(test_db, agent, age_seconds=60)
    other = sessionmaker(bind=test_db.get_bind())()
    try:
        other.query(AgentJob).filter(AgentJob.id == job.id).update(
            {AgentJob.status: status}, synchronize_session=False
        )
        other.commit()
    finally:
        other.close()
    test_db.expire_all()
    assert job.status == status  # the copy reloaded after the other pass

    sent = await agent_job_dispatcher.dispatch_agent_job_if_connected(test_db, job)

    assert sent is False
    websocket.send_json.assert_not_awaited()
    test_db.expire_all()
    assert test_db.get(AgentJob, job.id).status == status
