"""An agent's keepalive (an empty progress report, 0.1.7) must not wipe the
last real progress snapshot on the job."""

from datetime import datetime

import pytest

from app.api.agents import _apply_agent_job_progress
from app.core.security import get_password_hash
from app.database.models import AgentJob, AgentMachine


@pytest.mark.unit
def test_a_keepalive_keeps_the_last_progress_snapshot(test_db):
    agent = AgentMachine(
        name="progress-agent",
        agent_id="agt_progress",
        token_hash=get_password_hash("secret"),
        token_prefix="secret",
        status="online",
        capabilities=[],
    )
    test_db.add(agent)
    test_db.commit()
    job = AgentJob(
        agent_machine_id=agent.id,
        job_type="repository",
        status="running",
        payload={"job_kind": "repository.check"},
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    test_db.add(job)
    test_db.commit()

    _apply_agent_job_progress(job, test_db, {"progress_percent": 42})
    _apply_agent_job_progress(job, test_db, {})

    assert job.progress == {"progress_percent": 42}
    assert job.progress_percent == 42
