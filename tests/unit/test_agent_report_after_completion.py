"""A start or progress report must not reopen an operation that the agent's
completion closed meanwhile (#1366, for backups #1404).

The agent sends start, progress and log lines over its session and the
outcome over REST, so the last progress frames of a short job routinely reach
the server while `/complete` is being recorded. The completion runs in a
worker thread with its own session (`_record_job_completion`); a report
handled meanwhile has read the job as still active. If the completion
committed after that read, the report used to write `running` over the
operation's `completed`: a plan's inline maintenance step then closed it as
failed ("the service returned without recording a verdict"), and the backup
executor failed a backup whose archive exists ("backup returned no result"),
each next to a completed agent job. The report also wrote its counters over
the final ones the completion carries.

A progress report now takes a guarded write on the job row before anything
else: a job that is final by then keeps its outcome, and a job still active
stays locked until the report commits, so a completion recorded meanwhile
lands after it. On PostgreSQL that write waits for the completion's lock on
the job row. SQLite takes one writer at a time, so the orders are laid out
here: the report's copy of the job is read first, the completion commits
through its own session, then the report runs on that copy; or the report
writes first and the completion, in a thread, waits for its commit.
"""

import asyncio
import threading
import time
from datetime import datetime, timezone

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
from app.services.operations.backup_facade import BackupJobFacade
from app.services.operations.maintenance_start import finish_inline_maintenance
from app.services.operations.vocab import TERMINAL_STATUSES
from tests.utils.agent_jobs import agent_maintenance_job
from tests.utils.operations import seed_job_operation

# What the agent's last progress frame reports, and the final archive
# counters its completion carries.
PROGRESS = {"progress_percent": 97.5, "total_expected_size": 1000, "nfiles": 7}
FINAL_STATS = {"original_size": 1000, "nfiles": 10}


def _agent(db):
    agent = AgentMachine(
        name="report-race-agent",
        agent_id="agt_report_race",
        token_hash=get_password_hash("secret"),
        token_prefix="secret",
        status="online",
        capabilities=[],
    )
    db.add(agent)
    db.commit()
    return agent


def _setup_compact(db):
    agent = _agent(db)
    repository = Repository(name="report-race-repo", path="/report-race")
    db.add(repository)
    db.commit()
    started = datetime.now(timezone.utc)
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


def _setup_backup(db):
    agent = _agent(db)
    started = datetime.now(timezone.utc)
    operation = seed_job_operation(
        db,
        "backup",
        repository="/report-race",
        status="running",
        started_at=started,
    )
    db.commit()
    job = AgentJob(
        agent_machine_id=agent.id,
        job_type="backup",
        status="running",
        payload={
            "schema_version": 1,
            "job_kind": "backup.create",
            "repository": {"id": operation.repository_id},
        },
        operation_id=operation.id,
        claimed_at=started,
        started_at=started,
        start_notified_at=started,
        created_at=started,
        updated_at=started,
    )
    db.add(job)
    db.commit()
    return agent, operation, job


SETUPS = pytest.mark.parametrize(
    "setup", [_setup_compact, _setup_backup], ids=["compact", "backup"]
)


def _complete(agent, job_id):
    return _record_job_completion(
        job_id,
        AgentJobCompleteRequest(
            result={
                "return_code": 0,
                "archive_name": "race-archive",
                "archive_stats": FINAL_STATS,
            }
        ),
        agent.id,
    )


def _ws_progress(job, db):
    _apply_agent_job_progress(job, db, dict(PROGRESS))


def _ws_keepalive(job, db):
    _apply_agent_job_progress(job, db, {})


def _assert_verdict_kept(db, operation_id, job_id):
    """The verdict and the final counters stand, and the reader of the
    operation keeps them: a plan's inline step for maintenance, the backup
    executor (which fails a backup it finds unfinished) for a backup."""
    db.expire_all()
    job = db.get(AgentJob, job_id)
    assert job.status == "completed"
    assert job.nfiles == FINAL_STATS["nfiles"]
    finished = db.get(Operation, operation_id)
    assert finished.status == "completed"
    assert finished.progress_percent == 100
    if finished.kind == "backup":
        backup = BackupJobFacade(db, finished)
        assert finished.status in TERMINAL_STATUSES
        assert backup.archive_name == "race-archive"
        assert backup.nfiles == FINAL_STATS["nfiles"]
        return
    finish_inline_maintenance(db, finished, enqueue_followups=False)
    db.expire_all()
    finished = db.get(Operation, operation_id)
    assert finished.status == "completed"
    assert finished.error_message is None


@pytest.mark.unit
@SETUPS
@pytest.mark.parametrize(
    "report",
    [_ws_progress, _ws_keepalive],
    ids=["progress", "keepalive"],
)
def test_a_session_report_after_the_completion_keeps_its_verdict(
    test_db, setup, report
):
    agent, operation, job = setup(test_db)
    # The session handler loads the job while it is still active ...
    assert test_db.get(AgentJob, job.id).status == "running"
    # ... and the completion commits before the report writes.
    assert _complete(agent, job.id) == (True, "completed")
    report(job, test_db)
    test_db.commit()

    _assert_verdict_kept(test_db, operation.id, job.id)


@pytest.mark.unit
@SETUPS
def test_a_rest_progress_report_after_the_completion_keeps_its_verdict(test_db, setup):
    agent, operation, job = setup(test_db)
    assert test_db.get(AgentJob, job.id).status == "running"
    assert _complete(agent, job.id) == (True, "completed")

    response = asyncio.run(
        update_job_progress(
            job.id,
            AgentJobProgressRequest(**PROGRESS),
            current_agent=test_db.get(AgentMachine, agent.id),
            db=test_db,
        )
    )

    # the answer reads the job as the completion left it
    assert response.status == "completed"
    _assert_verdict_kept(test_db, operation.id, job.id)


@pytest.mark.unit
@SETUPS
def test_a_completion_during_a_report_lands_after_it(test_db, monkeypatch, setup):
    """The other order: the report writes while the job is active, and the
    completion arrives before the report commits. The completion waits for
    the report's lock on the job row and then writes its verdict and its
    counters over the report's."""
    agent, operation, job = setup(test_db)
    _ws_progress(job, test_db)

    at_terminal_write = threading.Event()
    original = agents._claim_terminal_transition

    def claim(*args, **kwargs):
        at_terminal_write.set()
        return original(*args, **kwargs)

    monkeypatch.setattr(agents, "_claim_terminal_transition", claim)
    outcome = []
    completion = threading.Thread(
        target=lambda: outcome.append(_complete(agent, job.id))
    )
    completion.start()
    assert at_terminal_write.wait(timeout=10)
    time.sleep(0.3)
    # the completion's terminal write waits for the report's commit
    assert completion.is_alive()
    assert outcome == []
    test_db.commit()
    completion.join(timeout=30)

    assert outcome == [(True, "completed")]
    _assert_verdict_kept(test_db, operation.id, job.id)


@pytest.mark.unit
def test_a_start_report_racing_the_completion_keeps_its_verdict(test_db):
    """A repeated start report takes a guarded write on the job before it
    reaches the operation. On PostgreSQL that write waits for the
    completion's lock on the job row, so the report has read the job before
    the completion committed and reads the operation after it. SQLite takes
    one writer at a time, so the order is laid out here: the report's copy
    of the job is read first, the completion commits, then the report runs
    on that copy."""
    agent, operation, job = _setup_compact(test_db)
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
def test_a_report_before_the_completion_still_records_its_progress(test_db):
    """The guard leaves the normal order alone: a report on an active job
    still records its start and progress on the operation. The operation
    has the shape a plan's inline step creates (`running`, no start yet);
    an agent maintenance operation is `running` before its agent job is
    queued, and goes back to `queued` only when admission refused the job,
    so a live agent job never carries a queued operation."""
    agent, operation, job = _setup_compact(test_db)
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


@pytest.mark.unit
def test_a_report_before_a_backup_completion_still_records_its_progress(test_db):
    agent, operation, job = _setup_backup(test_db)

    _apply_agent_job_progress(
        job,
        test_db,
        {
            "progress_percent": 40,
            "total_expected_size": 1000,
            "current_file": "/data/file-7",
            "nfiles": 7,
        },
    )
    test_db.commit()

    test_db.expire_all()
    reported = test_db.get(Operation, operation.id)
    assert reported.status == "running"
    assert reported.progress_percent == 40
    backup = BackupJobFacade(test_db, reported)
    assert backup.current_file == "/data/file-7"
    assert backup.nfiles == 7
    assert test_db.get(AgentJob, job.id).nfiles == 7
