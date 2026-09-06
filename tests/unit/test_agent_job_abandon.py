"""abandon_agent_repository_operation_job: a repository job the server
stopped waiting for must not stay queued, where the reaper never reaches it
and the admission counts it as active work."""

from datetime import datetime

import pytest
from sqlalchemy import create_engine, update
from sqlalchemy.orm import sessionmaker

from app.core.security import get_password_hash
from app.database.models import AgentJob, AgentMachine, Base
from app.services.repository_executor import abandon_agent_repository_operation_job


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def agent(db):
    machine = AgentMachine(
        name="agent",
        agent_id="agt_abandon",
        token_hash=get_password_hash("secret"),
        token_prefix="secret",
        status="active",
        capabilities=["repository.archive_info"],
    )
    db.add(machine)
    db.commit()
    return machine


def _job(db, agent, status):
    job = AgentJob(
        agent_machine_id=agent.id,
        job_type="repository",
        status=status,
        payload={"job_kind": "repository.archive_info", "repository": {"id": 1}},
        created_at=datetime(2026, 9, 7, 10, 0),
        updated_at=datetime(2026, 9, 7, 10, 0),
    )
    db.add(job)
    db.commit()
    return job


@pytest.mark.unit
@pytest.mark.parametrize(
    ("before", "after"),
    [
        ("queued", "canceled"),
        ("claimed", "cancel_requested"),
        ("running", "cancel_requested"),
        ("cancel_requested", "cancel_requested"),
        ("completed", "completed"),
        ("failed", "failed"),
        ("canceled", "canceled"),
    ],
)
def test_abandon_moves_only_live_jobs(db, agent, before, after):
    job = _job(db, agent, before)
    now = datetime(2026, 9, 7, 10, 30)
    returned = abandon_agent_repository_operation_job(db, job.id, now=now)
    db.expire_all()
    row = db.get(AgentJob, job.id)
    assert returned is not None and returned.id == row.id
    assert row.status == after
    if before == "queued":
        assert row.completed_at == now and "Abandoned" in row.error_message
        assert row.updated_at == now
    elif before in ("claimed", "running"):
        assert row.completed_at is None and row.updated_at == now
    else:
        assert row.updated_at == datetime(2026, 9, 7, 10, 0)


@pytest.mark.unit
def test_abandon_unknown_job_is_a_noop(db):
    assert abandon_agent_repository_operation_job(db, 4242) is None


@pytest.mark.unit
def test_abandon_loses_to_a_completion_that_landed_first(db, agent):
    """The agent's completion report can commit between the read and the
    write; the write is conditional on the status read, so a terminal job
    stays terminal instead of turning into cancel_requested."""
    job = _job(db, agent, "running")
    # completed by the report handler behind this session's back: the row
    # says completed, the identity map still holds "running" (no commit
    # here, a commit would expire it and hide the race)
    db.execute(
        update(AgentJob)
        .where(AgentJob.id == job.id)
        .values(
            status="completed",
            completed_at=datetime(2026, 9, 7, 10, 29),
            updated_at=datetime(2026, 9, 7, 10, 29),
        ),
        execution_options={"synchronize_session": False},
    )
    assert job.status == "running"
    returned = abandon_agent_repository_operation_job(
        db, job.id, now=datetime(2026, 9, 7, 10, 30)
    )
    assert returned is not None and returned.status == "completed"
    db.expire_all()
    row = db.get(AgentJob, job.id)
    assert row.status == "completed"
    assert row.completed_at == datetime(2026, 9, 7, 10, 29)
    # untouched by the abandonment: the report's timestamp stands
    assert row.updated_at == datetime(2026, 9, 7, 10, 29)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("read", "meanwhile", "after"),
    [
        ("queued", "claimed", "cancel_requested"),
        ("claimed", "running", "cancel_requested"),
    ],
)
def test_abandon_retries_after_a_live_transition(db, agent, read, meanwhile, after):
    """The agent claims or starts the job between the read and the write:
    the first conditional write matches nothing, the retry reads the new
    live state and still requests the cancel."""
    job = _job(db, agent, read)
    db.execute(
        update(AgentJob).where(AgentJob.id == job.id).values(status=meanwhile),
        execution_options={"synchronize_session": False},
    )
    assert job.status == read
    now = datetime(2026, 9, 7, 10, 30)
    returned = abandon_agent_repository_operation_job(db, job.id, now=now)
    assert returned is not None and returned.status == after
    db.expire_all()
    row = db.get(AgentJob, job.id)
    assert row.status == after and row.completed_at is None
    assert row.updated_at == now
