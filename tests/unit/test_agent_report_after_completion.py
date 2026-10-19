"""A start or progress report must not reopen an operation that the agent's
completion closed meanwhile (#1366).

The agent sends start, progress and log lines over its session and the
outcome over REST, so the last progress frames of a short job routinely reach
the server while `/complete` is being recorded. The completion runs in a
worker thread with its own session (`_record_job_completion`); a report
handled meanwhile has read the job as still active. If the completion commits
between that read and the report's read of the operation, the report used to
write `running` over the operation's `completed`, and a plan's inline step
then closed it as failed ("the service returned without recording a
verdict") next to a completed agent job.
"""

import asyncio
from datetime import datetime

import pytest

import app.api.agents as agents
from app.api.agents import (
    AgentJobCompleteRequest,
    AgentJobProgressRequest,
    _apply_agent_job_progress,
    _mark_agent_job_started,
    _record_job_completion,
    update_job_progress,
)
from app.core.security import get_password_hash
from app.database.models import AgentJob, AgentMachine, Operation, Repository
from app.services.operations.maintenance_start import finish_inline_maintenance
from tests.utils.agent_jobs import agent_maintenance_job


def _setup(db):
    agent = AgentMachine(
        name="report-race-agent",
        agent_id="agt_report_race",
        token_hash=get_password_hash("secret"),
        token_prefix="secret",
        status="online",
        capabilities=[],
    )
    repository = Repository(name="report-race-repo", path="/report-race")
    db.add_all([agent, repository])
    db.commit()
    started = datetime.utcnow()
    # Created as a plan's inline step creates it, already started.
    operation = Operation(
        repository_id=repository.id,
        kind="compact",
        category="maintenance",
        status="running",
        trigger="plan",
        priority=10,
        run_id="run-report-race",
        started_at=started,
    )
    db.add(operation)
    db.commit()
    job = agent_maintenance_job(
        db,
        agent,
        "compact",
        operation.id,
        repository=repository,
        claimed_at=started,
        started_at=started,
        start_notified_at=started,
        created_at=started,
        updated_at=started,
    )
    return agent, operation, job


def _complete_between_job_and_operation_read(monkeypatch, agent, job_id):
    """Commit the completion through its own session right after the report
    has read the job and before it reads the operation: the report path
    looks for a linked backup job in between."""
    original = agents._get_linked_backup_job
    calls, fired = [], []

    def completion_lands(job, db):
        # once, and not from inside the completion, which asks the same
        if not fired:
            fired.append(True)
            calls.append(
                _record_job_completion(
                    job_id,
                    AgentJobCompleteRequest(result={"return_code": 0}),
                    agent.id,
                )
            )
        return original(job, db)

    monkeypatch.setattr(agents, "_get_linked_backup_job", completion_lands)
    return calls


def _ws_progress(job, db):
    _apply_agent_job_progress(job, db, {"progress_percent": 2.5})


def _ws_keepalive(job, db):
    _apply_agent_job_progress(job, db, {})


@pytest.mark.unit
@pytest.mark.parametrize(
    "report",
    [_ws_progress, _ws_keepalive],
    ids=["progress", "keepalive"],
)
def test_a_session_report_racing_the_completion_keeps_its_verdict(
    test_db, monkeypatch, report
):
    agent, operation, job = _setup(test_db)
    calls = _complete_between_job_and_operation_read(monkeypatch, agent, job.id)

    # The session handler loads the job while it is still active ...
    assert test_db.get(AgentJob, job.id).status == "running"
    # ... and the completion commits before it reaches the operation.
    report(job, test_db)
    test_db.commit()

    assert calls == [(True, "completed")]
    test_db.expire_all()
    assert test_db.get(AgentJob, job.id).status == "completed"
    finished = test_db.get(Operation, operation.id)
    assert finished.status == "completed"
    assert finished.progress_percent == 100

    # The plan's inline step reads the operation once its wait sees the
    # completed agent job, and keeps the verdict.
    finish_inline_maintenance(test_db, finished, enqueue_followups=False)
    test_db.expire_all()
    finished = test_db.get(Operation, operation.id)
    assert finished.status == "completed"
    assert finished.error_message is None


@pytest.mark.unit
def test_a_rest_progress_report_racing_the_completion_keeps_its_verdict(
    test_db, monkeypatch
):
    agent, operation, job = _setup(test_db)
    calls = _complete_between_job_and_operation_read(monkeypatch, agent, job.id)

    response = asyncio.run(
        update_job_progress(
            job.id,
            AgentJobProgressRequest(progress_percent=2.5),
            current_agent=test_db.get(AgentMachine, agent.id),
            db=test_db,
        )
    )

    # the answer reads the job as the completion left it
    assert response.status == "completed"
    assert calls == [(True, "completed")]
    test_db.expire_all()
    finished = test_db.get(Operation, operation.id)
    assert finished.status == "completed"
    assert finished.progress_percent == 100


@pytest.mark.unit
def test_a_start_report_racing_the_completion_keeps_its_verdict(test_db):
    """A repeated start report takes a guarded write on the job before it
    reaches the operation. On PostgreSQL that write waits for the
    completion's lock on the job row, so the report has read the job before
    the completion committed and reads the operation after it. SQLite takes
    one writer at a time, so the order is laid out here: the report's copy
    of the job is read first, the completion commits, then the report runs
    on that copy."""
    agent, operation, job = _setup(test_db)
    assert test_db.get(AgentJob, job.id).status == "running"

    assert _record_job_completion(
        job.id, AgentJobCompleteRequest(result={"return_code": 0}), agent.id
    ) == (True, "completed")
    _mark_agent_job_started(job, test_db)
    test_db.commit()

    test_db.expire_all()
    assert test_db.get(AgentJob, job.id).status == "completed"
    finished = test_db.get(Operation, operation.id)
    assert finished.status == "completed"
    assert finished.progress_percent == 100


@pytest.mark.unit
def test_a_report_that_read_the_operation_first_keeps_its_verdict(test_db):
    """The other order: the report reads job and operation while both are
    active, and the completion commits before the report does. The report
    writes only what it changed, and `running` on a `running` row is no
    change, so the verdict stays. Its progress figures can still land
    after the completion's; the status is what the plan reads."""
    agent, operation, job = _setup(test_db)

    _apply_agent_job_progress(job, test_db, {"progress_percent": 2.5})
    assert _record_job_completion(
        job.id, AgentJobCompleteRequest(result={"return_code": 0}), agent.id
    ) == (True, "completed")
    test_db.commit()

    test_db.expire_all()
    finished = test_db.get(Operation, operation.id)
    assert finished.status == "completed"
    finish_inline_maintenance(test_db, finished, enqueue_followups=False)
    test_db.expire_all()
    assert test_db.get(Operation, operation.id).status == "completed"


@pytest.mark.unit
def test_a_report_before_the_completion_still_records_its_progress(test_db):
    """The guard leaves the normal order alone: a report on an active job
    still records its start and progress on the operation. The operation
    has the shape a plan's inline step creates (`running`, no start yet);
    an agent maintenance operation is `running` before its agent job is
    queued, and goes back to `queued` only when admission refused the job,
    so a live agent job never carries a queued operation."""
    agent, operation, job = _setup(test_db)
    operation.started_at = None
    test_db.commit()

    _apply_agent_job_progress(
        job, test_db, {"progress_percent": 40, "current_file": "segment 7"}
    )
    test_db.commit()

    test_db.expire_all()
    reported = test_db.get(Operation, operation.id)
    assert reported.status == "running"
    assert reported.started_at is not None
    assert reported.progress_percent == 40
    assert reported.progress_message == "segment 7"
