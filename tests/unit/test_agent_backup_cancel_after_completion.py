"""A cancel of an agent backup must not reopen an agent job that its
completion closed meanwhile (#1404).

The completion is recorded in a worker thread with its own session
(`_record_job_completion`), so a cancel handled meanwhile may hold a copy of
the agent job that still reads `running`. Its write of `cancel_requested`
used to be a plain attribute on that copy: the completed job went back to
`cancel_requested`, the executor's wait no longer saw a final job and kept
polling until the reaper ended it. The write is now conditional on the
status the cancel read, as the maintenance cancel's is.

SQLite takes one writer at a time, so the orders are laid out here: the
cancel's copy is read first, the other writer commits through its own
session, then the cancel runs on that copy.
"""

import asyncio
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

import app.services.repository_executor as repository_executor
from app.api.agents import AgentJobCompleteRequest, _record_job_completion
from app.core.security import get_password_hash
import app.database.database as database
from app.database.models import AgentJob, AgentMachine, Operation
from app.services.operations.backup_facade import resolve_backup_job
from app.services.repository_executor import (
    cancel_agent_backup_job,
    get_agent_job_for_backup,
    wait_for_agent_backup_job,
)
from tests.utils.operations import seed_job_operation


def _setup(db, *, status="running"):
    agent = AgentMachine(
        name="cancel-race-agent",
        agent_id="agt_cancel_race",
        token_hash=get_password_hash("secret"),
        token_prefix="secret",
        status="online",
        capabilities=[],
    )
    db.add(agent)
    db.commit()
    now = datetime.now(timezone.utc)
    operation = seed_job_operation(
        db, "backup", repository="/cancel-race", status="running", started_at=now
    )
    db.commit()
    job = AgentJob(
        agent_machine_id=agent.id,
        job_type="backup",
        status=status,
        payload={
            "schema_version": 1,
            "job_kind": "backup.create",
            "repository": {"id": operation.repository_id},
        },
        operation_id=operation.id,
        claimed_at=None if status == "queued" else now,
        started_at=now if status == "running" else None,
        created_at=now,
        updated_at=now,
    )
    db.add(job)
    db.commit()
    return agent, operation, job


def _complete(agent, job_id):
    return _record_job_completion(
        job_id, AgentJobCompleteRequest(result={"return_code": 0}), agent.id
    )


def _status(db, model, row_id):
    db.expire_all()
    return db.get(model, row_id).status


@pytest.mark.unit
def test_a_cancel_after_the_completion_keeps_the_job_completed(test_db):
    agent, operation, job = _setup(test_db)
    # The cancel's copies, read as the route and the executor read them:
    # the backup, then its agent job.
    backup = resolve_backup_job(test_db, operation.id)
    assert get_agent_job_for_backup(test_db, backup).status == "running"

    assert _complete(agent, job.id) == (True, "completed")
    with pytest.raises(HTTPException) as refused:
        cancel_agent_backup_job(test_db, backup)
    test_db.commit()

    assert refused.value.status_code == 400
    assert _status(test_db, AgentJob, job.id) == "completed"
    assert _status(test_db, Operation, operation.id) == "completed"


@pytest.mark.unit
def test_a_cancel_after_a_claim_asks_the_agent_to_stop(test_db):
    """A claim between the cancel's read and its write is not a final state:
    the cancel reads again and asks the agent to stop instead of cancelling
    a job the agent holds."""
    agent, operation, job = _setup(test_db, status="queued")
    backup = resolve_backup_job(test_db, operation.id)
    assert get_agent_job_for_backup(test_db, backup).status == "queued"

    # through the session factory the completion uses as well
    other = database.SessionLocal()
    try:
        other.get(AgentJob, job.id).status = "claimed"
        other.commit()
    finally:
        other.close()
    agent_job, _ = cancel_agent_backup_job(test_db, backup)
    test_db.commit()

    assert agent_job.status == "cancel_requested"
    assert _status(test_db, AgentJob, job.id) == "cancel_requested"
    assert _status(test_db, Operation, operation.id) == "running"


@pytest.mark.unit
def test_a_cancel_of_a_running_job_asks_the_agent_to_stop(test_db):
    agent, operation, job = _setup(test_db)
    backup = resolve_backup_job(test_db, operation.id)

    agent_job, _ = cancel_agent_backup_job(test_db, backup)
    test_db.commit()

    assert agent_job.status == "cancel_requested"
    assert _status(test_db, AgentJob, job.id) == "cancel_requested"
    assert _status(test_db, Operation, operation.id) == "running"


@pytest.mark.unit
def test_the_wait_reads_a_completion_that_beat_its_cancel(test_db, monkeypatch):
    """The executor's wait cancels a job it read as live. When the completion
    commits between that read and the cancel, the wait returns the verdict
    instead of reopening the job and polling on."""
    agent, operation, job = _setup(test_db)
    original = repository_executor.resolve_backup_job
    fired = []

    def completion_lands(db, operation_id):
        # the wait has read the agent job; the completion commits now
        if not fired:
            fired.append(_complete(agent, job.id))
        return original(db, operation_id)

    monkeypatch.setattr(repository_executor, "resolve_backup_job", completion_lands)

    verdict = asyncio.run(
        asyncio.wait_for(
            wait_for_agent_backup_job(
                test_db,
                job.id,
                operation.id,
                lambda: True,
                poll_interval_seconds=0.01,
            ),
            timeout=5,
        )
    )

    assert fired == [(True, "completed")]
    assert verdict == "completed"
    assert _status(test_db, AgentJob, job.id) == "completed"
    assert _status(test_db, Operation, operation.id) == "completed"
