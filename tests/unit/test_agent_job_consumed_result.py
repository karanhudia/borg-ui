"""wait_for_agent_repository_operation_job hands its caller the full result
of a machine-parsed job and reduces the stored copy to what still describes
the run; other kinds and failed jobs keep their rows as they are.

The reduction writes through a session of its own, so these tests run on a
file database: an in-memory SQLite hands every session one connection, and
there the wait leaves the row to the retention pass (tested last)."""

from datetime import datetime

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, event
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

from app.core.security import get_password_hash
from app.database.models import AgentJob, AgentMachine, Base
from app.services.repository_executor import (
    MACHINE_PARSED_JOB_KINDS,
    consumed_result,
    wait_for_agent_repository_operation_job,
)

FULL_RESULT = {
    "return_code": 0,
    "command": ["borg", "list", "--json"],
    "stdout": '{"archives": [{"name": "a1"}]}',
    "stderr": "",
    "data": {"archives": [{"name": "a1"}]},
}
CONSUMED = {"return_code": 0, "command": ["borg", "list", "--json"], "stderr": ""}


@pytest.fixture()
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path}/jobs.db")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def agent_factory():
    def make(session):
        machine = AgentMachine(
            name="agent",
            agent_id="agt_consumed",
            token_hash=get_password_hash("secret"),
            token_prefix="secret",
            status="active",
            capabilities=sorted(MACHINE_PARSED_JOB_KINDS),
        )
        session.add(machine)
        session.commit()
        return machine

    return make


@pytest.fixture()
def agent(db, agent_factory):
    return agent_factory(db)


def _job(db, agent, job_kind, *, status="completed", result=None):
    when = datetime(2026, 9, 14, 10, 0)
    job = AgentJob(
        agent_machine_id=agent.id,
        job_type="repository",
        status=status,
        payload={"job_kind": job_kind, "repository": {"id": 1}},
        result=dict(FULL_RESULT) if result is None else result,
        created_at=when,
        updated_at=when,
        completed_at=when,
    )
    db.add(job)
    db.commit()
    return job


def _stored(db, job_id):
    db.expire_all()
    return db.get(AgentJob, job_id).result


@pytest.mark.unit
@pytest.mark.parametrize("job_kind", sorted(MACHINE_PARSED_JOB_KINDS))
async def test_wait_returns_full_result_and_reduces_row(db, agent, job_kind):
    job = _job(db, agent, job_kind)
    result = await wait_for_agent_repository_operation_job(db, job.id)
    assert result == FULL_RESULT
    assert _stored(db, job.id) == CONSUMED
    assert db.get(AgentJob, job.id).status == "completed"


@pytest.mark.unit
async def test_warning_completion_is_reduced_too(db, agent):
    job = _job(
        db,
        agent,
        "repository.list_archives",
        status="completed_with_warnings",
        result={**FULL_RESULT, "return_code": 1},
    )
    result = await wait_for_agent_repository_operation_job(db, job.id)
    assert result["return_code"] == 1 and result["data"] == FULL_RESULT["data"]
    assert _stored(db, job.id) == {**CONSUMED, "return_code": 1}


@pytest.mark.unit
@pytest.mark.parametrize(
    "job_kind", ["repository.list_archive_contents", "repository.prune"]
)
async def test_other_kinds_keep_their_result(db, agent, job_kind):
    job = _job(db, agent, job_kind)
    assert await wait_for_agent_repository_operation_job(db, job.id) == FULL_RESULT
    assert _stored(db, job.id) == FULL_RESULT


@pytest.mark.unit
async def test_failed_job_keeps_its_result(db, agent):
    job = _job(db, agent, "repository.list_archives", status="failed")
    with pytest.raises(HTTPException) as excinfo:
        await wait_for_agent_repository_operation_job(db, job.id)
    assert excinfo.value.status_code == 502
    assert _stored(db, job.id) == FULL_RESULT


@pytest.mark.unit
async def test_reduced_row_is_not_written_again(db, agent):
    job = _job(db, agent, "repository.list_archives", result=dict(CONSUMED))
    updates = []

    @event.listens_for(db.get_bind(), "before_cursor_execute")
    def _count(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("UPDATE"):
            updates.append(statement)

    assert await wait_for_agent_repository_operation_job(db, job.id) == CONSUMED
    assert updates == []


@pytest.mark.unit
async def test_reduction_failure_leaves_the_row_and_the_result(db, agent):
    """The reduction is best effort: a failed write is rolled back and the
    caller still gets the full result on a usable session."""
    job = _job(db, agent, "repository.list_archives")

    @event.listens_for(db.get_bind(), "before_cursor_execute")
    def _fail_updates(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("UPDATE"):
            raise OperationalError(statement, parameters, Exception("locked"))

    result = await wait_for_agent_repository_operation_job(db, job.id)
    assert result == FULL_RESULT
    assert _stored(db, job.id) == FULL_RESULT
    assert db.query(AgentJob).count() == 1


@pytest.mark.unit
async def test_reduction_leaves_the_callers_transaction_alone(db, agent):
    """Unrelated pending state of the caller is neither committed by the
    reduction nor lost with it: the caller's rollback still takes it away,
    the reduced row stays. The state is pending, not flushed: a caller that
    held SQLite's one write lock through the wait would block the agent's
    completion report it is waiting for, so no caller does."""
    job = _job(db, agent, "repository.list_archives")
    db.add(AgentJob(agent_machine_id=agent.id, job_type="backup", payload={}))
    assert await wait_for_agent_repository_operation_job(db, job.id) == FULL_RESULT
    db.rollback()
    assert db.query(AgentJob).count() == 1
    assert _stored(db, job.id) == CONSUMED


@pytest.mark.unit
async def test_shared_connection_leaves_the_row_to_retention(agent_factory):
    """An in-memory SQLite hands every session the same connection, so a
    commit of its own would commit the caller's pending state too: no
    reduction there, and the caller's state stays the caller's."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine, autoflush=False)()
    try:
        agent = agent_factory(db)
        job = _job(db, agent, "repository.list_archives")
        db.add(AgentJob(agent_machine_id=agent.id, job_type="backup", payload={}))
        db.flush()
        result = await wait_for_agent_repository_operation_job(db, job.id)
        assert result == FULL_RESULT
        db.rollback()
        assert db.query(AgentJob).count() == 1
        assert _stored(db, job.id) == FULL_RESULT
    finally:
        db.close()


@pytest.mark.unit
def test_consumed_result_keeps_only_the_small_fields():
    assert consumed_result(FULL_RESULT) == CONSUMED
    assert consumed_result({"return_code": 0}) == {"return_code": 0}
    assert consumed_result("not a dict") == {}
    assert consumed_result(None) == {}
