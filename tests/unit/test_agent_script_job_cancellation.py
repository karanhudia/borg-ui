"""A cancelled/timed-out agent ``script.run`` job must be persisted to a
non-dispatchable terminal state, so an offline agent's fallback dispatch can
never run the script *after* the plan gave up waiting."""

from unittest.mock import AsyncMock, patch

import pytest

from app.core.security import get_password_hash
from app.database.models import AgentJob, AgentMachine
from app.services import repository_executor
from app.services.repository_executor import wait_for_agent_script_job


def _queued_script_job(db_session):
    agent = AgentMachine(
        name="Agent",
        agent_id="agt_script",
        token_hash=get_password_hash("agent-secret"),
        token_prefix="agent-secret",
        status="offline",
    )
    db_session.add(agent)
    db_session.flush()
    job = AgentJob(
        agent_machine_id=agent.id,
        job_type="script",
        status="queued",
        payload={"schema_version": 1, "job_kind": "script.run"},
    )
    db_session.add(job)
    db_session.commit()
    return job


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cancel_persists_terminal_state_for_offline_agent(db_session):
    job = _queued_script_job(db_session)

    # Agent offline: the best-effort remote cancel is a no-op and does NOT move
    # the job out of "queued" by itself.
    with patch.object(
        repository_executor, "dispatch_agent_cancel_if_connected", new=AsyncMock()
    ) as remote_cancel:
        result = await wait_for_agent_script_job(
            db_session,
            job.id,
            is_cancelled=lambda: True,
            timeout_seconds=30,
        )

    remote_cancel.assert_awaited_once()
    assert result["status"] == "canceled"
    # Persisted terminal state is the real guarantee: a "queued" job would still
    # be picked up by fallback dispatch and run later.
    db_session.expire_all()
    assert db_session.get(AgentJob, job.id).status == "canceled"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_timeout_persists_terminal_state_for_offline_agent(db_session):
    job = _queued_script_job(db_session)

    with patch.object(
        repository_executor, "dispatch_agent_cancel_if_connected", new=AsyncMock()
    ):
        result = await wait_for_agent_script_job(
            db_session,
            job.id,
            timeout_seconds=0,
        )

    assert result["status"] == "timeout"
    db_session.expire_all()
    assert db_session.get(AgentJob, job.id).status == "canceled"
