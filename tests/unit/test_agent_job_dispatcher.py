from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.services import agent_job_dispatcher


@pytest.mark.unit
@pytest.mark.asyncio
async def test_best_effort_dispatch_rolls_back_and_filters_log_context(monkeypatch):
    async def raise_dispatch_error(*args, **kwargs):
        raise RuntimeError("dispatch failed")

    warning_calls = []

    monkeypatch.setattr(
        agent_job_dispatcher,
        "dispatch_agent_job_if_connected",
        raise_dispatch_error,
    )
    monkeypatch.setattr(
        agent_job_dispatcher,
        "logger",
        SimpleNamespace(
            warning=lambda *args, **kwargs: warning_calls.append((args, kwargs))
        ),
    )
    db = SimpleNamespace(rollback=Mock())
    job = SimpleNamespace(id=17, agent_machine_id=23)

    result = await agent_job_dispatcher.dispatch_agent_job_best_effort(
        db,
        job,
        error="caller error",
        agent_job_id=999,
        agent_machine_id=888,
        repository_id=5,
    )

    assert result is False
    db.rollback.assert_called_once_with()
    assert len(warning_calls) == 1
    _, log_context = warning_calls[0]
    assert log_context["error"] == "dispatch failed"
    assert log_context["agent_job_id"] == 17
    assert log_context["agent_machine_id"] == 23
    assert log_context["repository_id"] == 5


def _queued_job(db):
    from datetime import datetime

    from app.core.security import get_password_hash
    from app.database.models import AgentJob, AgentMachine

    agent = AgentMachine(
        name="dispatch-agent",
        agent_id="agt_dispatch",
        token_hash=get_password_hash("secret"),
        token_prefix="secret",
        status="online",
        capabilities=[],
    )
    db.add(agent)
    db.commit()
    job = AgentJob(
        agent_machine_id=agent.id,
        job_type="repository",
        status="queued",
        payload={"job_kind": "repository.delete_archive"},
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(job)
    db.commit()
    return job


@pytest.mark.unit
@pytest.mark.asyncio
async def test_a_job_cancelled_after_it_was_loaded_is_not_sent(test_db, monkeypatch):
    """A caller's copy still reads `queued` while a cancel took the job off
    the queue: the claim is conditional, so nothing reaches the agent."""
    from unittest.mock import AsyncMock

    from app.database.models import AgentJob

    from sqlalchemy.orm import sessionmaker

    job = _queued_job(test_db)
    assert job.status == "queued"  # loaded by the caller
    other = sessionmaker(bind=test_db.get_bind())()
    try:
        other.query(AgentJob).filter(AgentJob.id == job.id).update(
            {AgentJob.status: "canceled"}, synchronize_session=False
        )
        other.commit()
    finally:
        other.close()
    assert job.status == "queued"  # the caller's copy is stale
    send = AsyncMock()
    manager = agent_job_dispatcher.agent_connection_manager
    monkeypatch.setattr(manager, "is_connected", lambda agent_machine_id: True)
    monkeypatch.setattr(manager, "send_command", send)

    sent = await agent_job_dispatcher.dispatch_agent_job_if_connected(test_db, job)

    assert sent is False
    send.assert_not_awaited()
    test_db.expire_all()
    assert test_db.get(AgentJob, job.id).status == "canceled"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_a_failed_send_puts_the_job_back_on_the_queue(test_db, monkeypatch):
    from unittest.mock import AsyncMock

    from app.database.models import AgentJob

    job = _queued_job(test_db)
    manager = agent_job_dispatcher.agent_connection_manager
    monkeypatch.setattr(manager, "is_connected", lambda agent_machine_id: True)
    monkeypatch.setattr(
        manager, "send_command", AsyncMock(side_effect=RuntimeError("socket closed"))
    )

    sent = await agent_job_dispatcher.dispatch_agent_job_if_connected(test_db, job)

    assert sent is False
    test_db.expire_all()
    assert test_db.get(AgentJob, job.id).status == "queued"


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["canceled", "cancel_requested"])
async def test_a_job_that_reads_cancelled_is_not_sent(test_db, monkeypatch, status):
    """A batch dispatch reloads the next job after committing the first;
    one cancelled meanwhile is not sent."""
    from unittest.mock import AsyncMock

    from app.database.models import AgentJob

    job = _queued_job(test_db)
    job.status = status
    test_db.commit()
    send = AsyncMock()
    manager = agent_job_dispatcher.agent_connection_manager
    monkeypatch.setattr(manager, "is_connected", lambda agent_machine_id: True)
    monkeypatch.setattr(manager, "send_command", send)

    sent = await agent_job_dispatcher.dispatch_agent_job_if_connected(test_db, job)

    assert sent is False
    send.assert_not_awaited()
    test_db.expire_all()
    assert test_db.get(AgentJob, job.id).status == status
