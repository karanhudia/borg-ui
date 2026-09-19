"""A polling agent's claim must not revive a job a cancel took off the queue
after the claim read it."""

from datetime import datetime
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import sessionmaker

from app.api import agents
from app.core.security import get_password_hash
from app.database.models import AgentJob, AgentMachine


def _queued_job(db):
    agent = AgentMachine(
        name="claim-agent",
        agent_id="agt_claim",
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
    return agent, job


@pytest.mark.unit
@pytest.mark.asyncio
async def test_a_claim_loses_to_a_cancel_that_landed_after_its_read(test_db):
    agent, job = _queued_job(test_db)
    real_get = agents._get_agent_job

    def read_then_cancel(job_id, current_agent, db):
        loaded = real_get(job_id, current_agent, db)
        # the cancel commits in another session between the read and the write
        other = sessionmaker(bind=db.get_bind())()
        try:
            other.query(AgentJob).filter(AgentJob.id == job_id).update(
                {AgentJob.status: "canceled"}, synchronize_session=False
            )
            other.commit()
        finally:
            other.close()
        return loaded

    with patch.object(agents, "_get_agent_job", read_then_cancel):
        with pytest.raises(HTTPException) as refused:
            await agents.claim_job(job.id, current_agent=agent, db=test_db)

    assert refused.value.status_code == 409
    test_db.expire_all()
    assert test_db.get(AgentJob, job.id).status == "canceled"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_a_queued_job_is_claimed(test_db):
    agent, job = _queued_job(test_db)

    response = await agents.claim_job(job.id, current_agent=agent, db=test_db)

    assert response.status == "claimed"
