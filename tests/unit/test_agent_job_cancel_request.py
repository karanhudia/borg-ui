"""An admin's cancel request must never reopen a finished agent job.

`request_agent_job_cancel` refuses every final status, `completed_with_warnings`
included, and writes `cancel_requested` only while the job is still
unfinished, so a verdict the agent commits after the check stands.
"""

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import sessionmaker

from app.api import agents, managed_machines
from app.core.security import get_password_hash
from app.database.models import AgentJob, AgentMachine, Operation
from tests.utils.operations import seed_job_operation

ADMIN = SimpleNamespace(username="admin")


def _job(db, status, *, operation_id=None):
    agent = AgentMachine(
        name="cancel-agent",
        agent_id="agt_cancel",
        token_hash=get_password_hash("secret"),
        token_prefix="secret",
        status="online",
        capabilities=[],
    )
    db.add(agent)
    db.commit()
    stale_at = agents._now_utc() - timedelta(minutes=10)
    job = AgentJob(
        agent_machine_id=agent.id,
        job_type="backup",
        status=status,
        payload={},
        operation_id=operation_id,
        claimed_at=stale_at,
        started_at=stale_at,
        created_at=stale_at,
        updated_at=stale_at,
    )
    db.add(job)
    db.commit()
    return agent, job


async def _request_cancel(db, job_id):
    with patch.object(
        managed_machines, "dispatch_agent_cancel_if_connected", AsyncMock()
    ) as dispatch:
        response = await managed_machines.request_agent_job_cancel(
            job_id, current_user=ADMIN, db=db
        )
    return response, dispatch


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize("status", sorted(agents.FINAL_AGENT_JOB_STATUSES))
async def test_a_finished_job_is_refused(test_db, status):
    _agent, job = _job(test_db, status)

    with pytest.raises(HTTPException) as refused:
        await _request_cancel(test_db, job.id)

    assert refused.value.status_code == 409
    test_db.expire_all()
    assert test_db.get(AgentJob, job.id).status == status


@pytest.mark.unit
@pytest.mark.asyncio
async def test_a_job_completed_with_warnings_keeps_its_backup_after_a_hello(test_db):
    # Accepted, the request used to turn into a cancel at the next hello and
    # report the finished backup as cancelled.
    backup = seed_job_operation(
        test_db, "backup", repository="/repo", status="completed"
    )
    test_db.commit()
    agent, job = _job(test_db, "completed_with_warnings", operation_id=backup.id)

    with pytest.raises(HTTPException):
        await _request_cancel(test_db, job.id)
    agents._requeue_stale_agent_jobs(
        test_db,
        agent,
        now=agents._now_utc(),
        running_job_ids=[],
        ignore_age_for_undelivered=True,
    )
    test_db.commit()
    test_db.expire_all()

    assert test_db.get(AgentJob, job.id).status == "completed_with_warnings"
    assert test_db.get(Operation, backup.id).status == "completed"


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize("verdict", ["completed", "completed_with_warnings", "failed"])
async def test_a_verdict_committed_after_the_check_stands(test_db, verdict):
    _agent, job = _job(test_db, "running")
    real_now = managed_machines._now_utc

    def commit_verdict_then_now():
        # The agent's report commits in another session between the
        # endpoint's check and its write.
        other = sessionmaker(bind=test_db.get_bind())()
        try:
            other.query(AgentJob).filter(AgentJob.id == job.id).update(
                {AgentJob.status: verdict}, synchronize_session=False
            )
            other.commit()
        finally:
            other.close()
        return real_now()

    with patch.object(managed_machines, "_now_utc", commit_verdict_then_now):
        with pytest.raises(HTTPException) as refused:
            await _request_cancel(test_db, job.id)

    assert refused.value.status_code == 409
    test_db.expire_all()
    assert test_db.get(AgentJob, job.id).status == verdict


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["queued", "claimed", "running"])
async def test_an_unfinished_job_is_asked_to_cancel(test_db, status):
    _agent, job = _job(test_db, status)

    response, dispatch = await _request_cancel(test_db, job.id)

    assert response.status == "cancel_requested"
    dispatch.assert_awaited_once()
    test_db.expire_all()
    assert test_db.get(AgentJob, job.id).status == "cancel_requested"
