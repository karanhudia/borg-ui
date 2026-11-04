"""Agent repository polling must leave pooled connections available to reporters."""

from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool

from app.database.models import AgentJob, AgentMachine, Base
from app.services import repository_executor


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["queued", "claimed", "running", "cancel_requested"])
async def test_repository_wait_releases_connection_while_agent_runs(
    tmp_path, monkeypatch, status
):
    engine = create_engine(
        f"sqlite:///{tmp_path}/wait.db",
        poolclass=QueuePool,
        pool_size=1,
        max_overflow=0,
        pool_timeout=0.05,
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, autoflush=False)
    db = sessions()
    try:
        agent = AgentMachine(
            name="agent", agent_id="agt_wait", token_hash="hash", token_prefix="prefix"
        )
        db.add(agent)
        db.flush()
        job = AgentJob(
            agent_machine_id=agent.id,
            job_type="repository",
            status=status,
            payload={"job_kind": "repository.check"},
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(job)
        db.flush()
        job_id = job.id
        db.commit()
        result = {"return_code": 0}
        sleeps = []

        async def complete_during_sleep(interval):
            sleeps.append(interval)
            # With one pooled connection, the completion report can progress
            # only if the waiter ended its idle read transaction.
            with sessions() as reporting_db:
                reporting_job = reporting_db.get(AgentJob, job_id)
                reporting_job.status = "completed"
                reporting_job.result = result
                reporting_db.commit()

        monkeypatch.setattr(repository_executor.asyncio, "sleep", complete_during_sleep)

        assert (
            await repository_executor.wait_for_agent_repository_operation_job(
                db, job_id, timeout_seconds=2, poll_interval_seconds=0.01
            )
            == result
        )
        assert sleeps == [0.01]
    finally:
        db.close()
        engine.dispose()
