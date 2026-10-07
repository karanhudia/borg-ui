"""A start report handled after the agent's completion must not set the
completed agent job back to running (#1376).

The agent sends its start report over the session and its outcome over REST
(`/complete`), so the two reach the server in either order. The completion is
recorded in a worker thread with its own session (`_record_job_completion`);
a start report handled meanwhile has read the job as still active. Its write
of `running` used to be a plain attribute on that copy, so its commit set the
`completed` job back to `running`, and a waiter on the job polled until its
timeout while admission held the repository until the reaper ended the job.

On PostgreSQL the report's guarded write waits for the completion's lock on
the job row, so the report has always read the job before the completion
committed. SQLite takes one writer at a time, so the order is laid out here:
the report's copy of the job is read first, the completion commits through
its own session, then the report runs on that copy.
"""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.orm import Session

import app.api.agents as agents
from app.api.agents import (
    AgentJobCompleteRequest,
    _handle_agent_session_message,
    _mark_agent_job_started,
    _record_job_completion,
)
from app.core.security import get_password_hash
from app.database.models import AgentJob, AgentMachine, Operation, Repository
from tests.utils.agent_jobs import agent_maintenance_job
from tests.utils.operations import seed_job_operation


def _agent(db):
    agent = AgentMachine(
        name="start-race-agent",
        agent_id="agt_start_race",
        token_hash=get_password_hash("secret"),
        token_prefix="secret",
        status="online",
        capabilities=[],
    )
    db.add(agent)
    db.commit()
    return agent


def _compact_job(db, agent):
    """A compact handed to the agent and claimed, its start not reported."""
    repository = Repository(name="start-race-repo", path="/start-race")
    db.add(repository)
    db.commit()
    now = datetime.now(timezone.utc)
    operation = Operation(
        repository_id=repository.id,
        kind="compact",
        category="maintenance",
        status="running",
        trigger="manual",
        priority=10,
        run_id="run-start-race",
        started_at=now,
    )
    db.add(operation)
    db.commit()
    job = agent_maintenance_job(
        db,
        agent,
        "compact",
        operation.id,
        repository=repository,
        status="claimed",
        claimed_at=now,
        created_at=now,
        updated_at=now,
    )
    return operation, job


def _backup_job(db, agent):
    """A backup handed to the agent and claimed, its start not reported."""
    operation = seed_job_operation(db, "backup", repository="/repo", status="running")
    db.commit()
    now = datetime.now(timezone.utc)
    job = AgentJob(
        agent_machine_id=agent.id,
        job_type="backup",
        status="claimed",
        payload={
            "schema_version": 1,
            "job_kind": "backup.create",
            "repository": {"id": 7},
        },
        operation_id=operation.id,
        claimed_at=now,
        created_at=now,
        updated_at=now,
    )
    db.add(job)
    db.commit()
    return operation, job


def _complete(agent, job_id):
    return _record_job_completion(
        job_id, AgentJobCompleteRequest(result={"return_code": 0}), agent.id
    )


def _status(db, model, row_id):
    db.expire_all()
    return db.get(model, row_id).status


@pytest.mark.unit
def test_a_start_report_after_the_completion_keeps_the_job_completed(test_db):
    agent = _agent(test_db)
    operation, job = _compact_job(test_db, agent)
    # The report's copy: still claimed.
    assert job.status == "claimed"

    assert _complete(agent, job.id) == (True, "completed")
    assert _mark_agent_job_started(job, test_db) is None
    test_db.commit()

    assert _status(test_db, AgentJob, job.id) == "completed"
    assert _status(test_db, Operation, operation.id) == "completed"


@pytest.mark.unit
def test_a_start_report_after_a_backup_completion_neither_reopens_nor_notifies(
    test_db,
):
    """The first start report of a backup claims the backup-start
    notification; once the outcome is in, a late one claims nothing and
    leaves the backup finished."""
    agent = _agent(test_db)
    operation, job = _backup_job(test_db, agent)
    assert job.status == "claimed"

    assert _complete(agent, job.id) == (True, "completed")
    assert _mark_agent_job_started(job, test_db) is None
    test_db.commit()

    assert _status(test_db, AgentJob, job.id) == "completed"
    assert _status(test_db, Operation, operation.id) == "completed"
    assert test_db.get(AgentJob, job.id).start_notified_at is None


@pytest.mark.unit
def test_a_session_start_report_racing_the_completion_keeps_the_job_completed(
    test_db, monkeypatch
):
    """The session path end to end: the completion commits right after the
    handler loaded the job."""
    agent = _agent(test_db)
    operation, job = _backup_job(test_db, agent)
    original = agents._load_session_job
    calls = []

    def completion_lands(db, agent_machine_id, job_id):
        loaded = original(db, agent_machine_id, job_id)
        calls.append(_complete(agent, loaded.id))
        return loaded

    monkeypatch.setattr(agents, "_load_session_job", completion_lands)
    notify = AsyncMock()
    monkeypatch.setattr(agents, "notify_backup_job_started", notify)

    asyncio.run(
        _handle_agent_session_message(
            test_db, agent.id, {"type": "job_started", "job_id": job.id}
        )
    )

    assert calls == [(True, "completed")]
    assert _status(test_db, AgentJob, job.id) == "completed"
    assert _status(test_db, Operation, operation.id) == "completed"
    notify.assert_not_awaited()


@pytest.mark.unit
def test_a_start_report_keeps_a_cancel_request_committed_meanwhile(test_db):
    """The same stale copy against a cancel request: the job stays
    `cancel_requested`, so the agent's cancel poll still ends borg."""
    agent = _agent(test_db)
    _operation, job = _compact_job(test_db, agent)
    assert job.status == "claimed"

    other = Session(bind=test_db.get_bind())
    try:
        other.query(AgentJob).filter(AgentJob.id == job.id).update(
            {AgentJob.status: "cancel_requested"}, synchronize_session=False
        )
        other.commit()
    finally:
        other.close()

    _mark_agent_job_started(job, test_db)
    test_db.commit()

    assert _status(test_db, AgentJob, job.id) == "cancel_requested"
    assert test_db.get(AgentJob, job.id).started_at is not None


@pytest.mark.unit
def test_a_start_report_before_the_completion_still_starts_the_job(test_db):
    """The guard leaves the normal order alone: the first start report
    marks the job and its backup running and claims the notification once;
    a completion after it finishes the job as before."""
    agent = _agent(test_db)
    operation, job = _backup_job(test_db, agent)
    started_at = datetime(2026, 10, 7, 12, 0, tzinfo=timezone.utc)

    started_backup = _mark_agent_job_started(job, test_db, started_at=started_at)
    test_db.commit()
    assert started_backup is not None
    assert started_backup.id == operation.id
    assert _status(test_db, AgentJob, job.id) == "running"
    assert _status(test_db, Operation, operation.id) == "running"
    reloaded = test_db.get(AgentJob, job.id)
    assert reloaded.started_at is not None
    assert reloaded.start_notified_at is not None

    # a repeated report changes nothing and does not notify again
    assert _mark_agent_job_started(reloaded, test_db) is None
    test_db.commit()
    assert _status(test_db, AgentJob, job.id) == "running"

    assert _complete(agent, job.id) == (True, "completed")
    assert _status(test_db, AgentJob, job.id) == "completed"
    assert _status(test_db, Operation, operation.id) == "completed"


@pytest.mark.unit
def test_a_start_report_on_a_cancel_requested_job_keeps_the_request(test_db):
    agent = _agent(test_db)
    _operation, job = _compact_job(test_db, agent)
    job.status = "cancel_requested"
    test_db.commit()

    _mark_agent_job_started(job, test_db)
    test_db.commit()

    assert _status(test_db, AgentJob, job.id) == "cancel_requested"
    assert test_db.get(AgentJob, job.id).started_at is not None
