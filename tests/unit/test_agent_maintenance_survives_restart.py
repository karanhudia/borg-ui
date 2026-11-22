"""Maintenance an agent runs goes on through a server restart.

As for a backup (`test_agent_backup_survives_restart.py`): a shutdown leaves
a check, prune, compact or archive deletion that an agent is running as it
is, and the next process waits on the same agent job again.
"""

import asyncio
from datetime import datetime

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

import app.database.database as database
import app.services.operations.runner as runner_module
from app.api.agents import (
    AgentJobCompleteRequest,
    AgentJobFailRequest,
    _record_job_completion,
    _record_job_failure,
)
from app.core.security import get_password_hash
from app.database.models import (
    AgentJob,
    AgentMachine,
    Base,
    Operation,
    Repository,
    SystemSettings,
)
from app.services.operations import executors
from app.services.operations.enqueue import enqueue
from app.services.operations.runner import OperationRunner

KINDS = {
    "check": {},
    "prune": {},
    "compact": {},
    "delete_archive": {"archive_name": "old-archive"},
}


@pytest.fixture()
def session_factory(tmp_path, monkeypatch):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'restart.db'}",
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def _pragmas(dbapi_conn, record):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")
        dbapi_conn.execute("PRAGMA busy_timeout=5000")

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    monkeypatch.setattr(database, "SessionLocal", factory)
    monkeypatch.setattr("app.config.settings.data_dir", str(tmp_path))
    executors.load_default_executors()
    # the follow-ups of a finished maintenance run are not this test's
    monkeypatch.setattr(runner_module, "enqueue_followups", lambda *a, **k: [])
    return factory


def _process(monkeypatch) -> OperationRunner:
    runner = OperationRunner(poll_interval=0.01)
    monkeypatch.setattr(runner_module, "operation_runner", runner)
    return runner


def _seed(db, kind):
    agent = AgentMachine(
        name="a",
        agent_id="agt_a",
        token_hash=get_password_hash("secret"),
        token_prefix="secret-a",
        status="online",
        capabilities=[
            "repository.check",
            "repository.prune",
            "repository.compact",
            "repository.delete_archive",
            "jobs.cancel",
        ],
        agent_version="0.1.25",
        created_at=datetime.utcnow(),
    )
    db.add(agent)
    db.add(SystemSettings())
    db.commit()
    repo = Repository(
        name="r",
        path="/repos/r",
        encryption="none",
        compression="lz4",
        repository_type="local",
        mode="full",
        borg_version=1,
        executor_type="agent",
        execution_target="agent",
        agent_machine_id=agent.id,
    )
    db.add(repo)
    db.commit()
    op = enqueue(
        db, kind, repository_id=repo.id, trigger="manual", params=dict(KINDS[kind])
    )
    db.commit()
    return agent.id, op.id


async def _start(factory, runner) -> int:
    """Dispatch the operation and let the agent claim and start its job."""
    assert runner.acquire_lease(factory())
    assert await runner.tick() == 1
    db = factory()
    try:
        job = None
        for _ in range(100):
            db.expire_all()
            job = db.query(AgentJob).first()
            if job is not None:
                break
            await asyncio.sleep(0.05)
        assert job is not None, "the executor queued no agent job"
        job.status = "running"
        job.claimed_at = job.started_at = datetime.utcnow()
        db.commit()
        return job.id
    finally:
        db.close()


def _state(factory, op_id, job_id):
    db = factory()
    try:
        return db.get(Operation, op_id).status, db.get(AgentJob, job_id).status
    finally:
        db.close()


async def _shut_down(runner) -> None:
    runner.stop()
    await asyncio.wait_for(runner.drain(timeout=20.0), timeout=5.0)


async def _restart(factory, monkeypatch) -> OperationRunner:
    replacement = _process(monkeypatch)
    assert replacement.acquire_lease(factory())
    db = factory()
    try:
        replacement.recover_on_startup(db)
    finally:
        db.close()
    replacement.attach_recovered()
    return replacement


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize("kind", sorted(KINDS))
async def test_agent_maintenance_goes_on_through_a_restart(
    session_factory, monkeypatch, kind
):
    agent_id, op_id = _seed(session_factory(), kind)
    runner = _process(monkeypatch)
    job_id = await _start(session_factory, runner)

    await _shut_down(runner)

    # no cancel is owed to the agent, and the record is not ended
    assert _state(session_factory, op_id, job_id) == ("running", "running")
    assert not runner.cancel_requested
    assert not runner._drain_timed_out

    replacement = await _restart(session_factory, monkeypatch)
    assert list(replacement.running_tasks) == [op_id]
    await asyncio.sleep(0.4)
    assert _state(session_factory, op_id, job_id) == ("running", "running")

    _record_job_completion(
        job_id, AgentJobCompleteRequest(result={"return_code": 0}), agent_id
    )
    await asyncio.wait_for(replacement.running_tasks[op_id], timeout=10.0)

    assert _state(session_factory, op_id, job_id) == ("completed", "completed")
    # the work was not queued a second time
    assert session_factory().query(AgentJob).count() == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_a_failure_the_agent_reports_after_the_restart_is_the_verdict(
    session_factory, monkeypatch
):
    agent_id, op_id = _seed(session_factory(), "check")
    runner = _process(monkeypatch)
    job_id = await _start(session_factory, runner)
    await _shut_down(runner)
    replacement = await _restart(session_factory, monkeypatch)

    _record_job_failure(
        job_id,
        AgentJobFailRequest(error_message="borg exited with code 2", return_code=2),
        agent_id,
    )
    await asyncio.wait_for(replacement.running_tasks[op_id], timeout=10.0)

    assert _state(session_factory, op_id, job_id) == ("failed", "failed")
    db = session_factory()
    assert "interrupted by restart" not in (
        db.get(Operation, op_id).error_message or ""
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_a_report_during_the_downtime_is_recorded_after_it(
    session_factory, monkeypatch
):
    agent_id, op_id = _seed(session_factory(), "compact")
    runner = _process(monkeypatch)
    job_id = await _start(session_factory, runner)
    await _shut_down(runner)

    replacement = await _restart(session_factory, monkeypatch)
    # redelivered by the agent before the new task first looked at the job
    _record_job_completion(
        job_id, AgentJobCompleteRequest(result={"return_code": 0}), agent_id
    )
    await asyncio.wait_for(replacement.running_tasks[op_id], timeout=10.0)

    assert _state(session_factory, op_id, job_id) == ("completed", "completed")
    assert session_factory().query(AgentJob).count() == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_maintenance_without_a_live_agent_job_fails_as_before(
    session_factory, monkeypatch
):
    agent_id, op_id = _seed(session_factory(), "prune")
    runner = _process(monkeypatch)
    job_id = await _start(session_factory, runner)
    await _shut_down(runner)
    db = session_factory()
    db.get(AgentJob, job_id).status = "failed"
    db.commit()
    db.close()

    replacement = await _restart(session_factory, monkeypatch)

    assert not replacement.running_tasks
    db = session_factory()
    op = db.get(Operation, op_id)
    assert (op.status, op.error_message) == ("failed", "interrupted by restart")
