"""A requeued agent job must keep the retry's log lines (#1378).

The agent numbers the log lines of every run from 0, and both log paths
treat a known (agent_job_id, sequence) as a duplicate. When a started job
went back to "queued", its first run's rows stayed, so the retry's first
lines were dropped and the job's log was the first run followed by the tail
of the retry - the transcript the completion stores, and the one prune and
compact read archive names and statistics from.

A requeue now drops the stored lines and leaves one row before the next
run's, saying the job was queued again. A prune keeps the lines naming the
archives it removed: Borg 1 commits a prune at checkpoints, so those may be
gone, and the next run does not name them again. A line of the stopped run
that arrives later is dropped by its attempt (#1383).
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.agents import (
    REQUEUED_JOB_LOG_MESSAGE,
    REQUEUED_JOB_LOG_SEQUENCE,
    _append_agent_job_log,
    _collect_agent_logs,
    _now_utc,
    _requeue_stale_agent_jobs,
)
from app.core.security import get_password_hash
from app.database.models import (
    AgentJob,
    AgentJobLog,
    AgentMachine,
    Operation,
    OperationBackupDetails,
    Repository,
)
from app.services.agent_job_dispatcher import agent_job_attempt
from app.services.repository_executor import _agent_job_failure_message
from tests.unit.test_api_agents import (
    _agent_headers,
    _create_agent_job,
    _create_enrollment_token,
    _get_agent,
    _register_agent,
)
from tests.utils.agent_jobs import agent_maintenance_job
from tests.utils.operations import seed_job_operation

FIRST_RUN = ["run 1: line 0", "run 1: line 1", "run 1: line 2"]
RETRY = ["run 2: line 0", "run 2: line 1"]
REQUEUED_LOG = "\n".join([REQUEUED_JOB_LOG_MESSAGE, *RETRY])


def _store_lines(db, job, lines, *, stream="stdout"):
    for sequence, message in enumerate(lines):
        db.add(
            AgentJobLog(
                agent_job_id=job.id,
                sequence=sequence,
                stream=stream,
                message=message,
                created_at=_now_utc(),
            )
        )
    db.commit()


def _heartbeat(test_client, registered, headers):
    response = test_client.post(
        "/api/agents/heartbeat",
        json={
            "agent_id": registered["agent_id"],
            "agent_version": "0.1.1",
            "borg_versions": [],
            "capabilities": ["backup.create"],
            "running_job_ids": [],
        },
        headers=headers,
    )
    assert response.status_code == 200


def _make_stale(db, job):
    stale_at = datetime.now(timezone.utc) - timedelta(minutes=30)
    job.status = "running"
    job.claimed_at = stale_at
    job.started_at = stale_at
    job.updated_at = stale_at
    db.commit()


def _rerun(test_client, job, headers, lines, *, stream="stdout"):
    assert (
        test_client.post(f"/api/agents/jobs/{job.id}/claim", headers=headers)
    ).status_code == 200
    assert (
        test_client.post(f"/api/agents/jobs/{job.id}/start", json={}, headers=headers)
    ).status_code == 200
    for sequence, message in enumerate(lines):
        uploaded = test_client.post(
            f"/api/agents/jobs/{job.id}/logs",
            json={"sequence": sequence, "stream": stream, "message": message},
            headers=headers,
        )
        assert uploaded.status_code == 200
        assert uploaded.json() == {"accepted": True, "duplicate": False}


@pytest.mark.unit
def test_heartbeat_requeue_keeps_the_retrys_uploaded_lines(
    test_client: TestClient, test_db, admin_headers
):
    registered = _register_agent(
        test_client,
        _create_enrollment_token(test_client, admin_headers)["token"],
    )
    agent = _get_agent(test_db, registered["agent_id"])
    headers = _agent_headers(registered["agent_token"])
    job = _create_agent_job(test_db, agent)
    _make_stale(test_db, job)
    _store_lines(test_db, job, FIRST_RUN)

    _heartbeat(test_client, registered, headers)
    test_db.refresh(job)
    assert job.status == "queued"

    _rerun(test_client, job, headers, RETRY)

    test_db.expire_all()
    assert _collect_agent_logs(job, test_db) == REQUEUED_LOG


@pytest.mark.unit
def test_a_late_line_of_the_stopped_run_does_not_take_the_retrys_place(
    test_client: TestClient, test_db, admin_headers
):
    # The requeue removes what the stopped run stored; a line of that run
    # still in flight carries its attempt and is dropped, before the job is
    # dispatched again and after.
    registered = _register_agent(
        test_client,
        _create_enrollment_token(test_client, admin_headers)["token"],
    )
    agent = _get_agent(test_db, registered["agent_id"])
    headers = _agent_headers(registered["agent_token"])
    job = _create_agent_job(test_db, agent)
    _make_stale(test_db, job)
    _store_lines(test_db, job, FIRST_RUN)
    stopped_attempt = agent_job_attempt(job)

    def upload(sequence, message, attempt):
        response = test_client.post(
            f"/api/agents/jobs/{job.id}/logs",
            json={"sequence": sequence, "message": message, "attempt": attempt},
            headers=headers,
        )
        assert response.status_code == 200
        return response.json()

    _heartbeat(test_client, registered, headers)
    test_db.refresh(job)
    assert job.status == "queued"
    assert upload(0, "run 1: late line", stopped_attempt)["superseded"] is True

    assert (
        test_client.post(f"/api/agents/jobs/{job.id}/claim", headers=headers)
    ).status_code == 200
    test_db.refresh(job)
    retry_attempt = agent_job_attempt(job)
    assert retry_attempt != stopped_attempt
    assert upload(1, "run 1: later line", stopped_attempt)["superseded"] is True
    for sequence, message in enumerate(RETRY):
        assert upload(sequence, message, retry_attempt) == {
            "accepted": True,
            "duplicate": False,
        }

    test_db.expire_all()
    assert _collect_agent_logs(job, test_db) == REQUEUED_LOG


@pytest.mark.unit
def test_a_prune_that_ran_twice_marks_the_archives_of_both_runs(
    test_client: TestClient, test_db, admin_headers
):
    # The completion writes the operation's log from the rows, and prune
    # marks the backup jobs of the archives that log names. The first run
    # removed an archive before it was cut off; the retry names only what
    # it removed itself.
    registered = _register_agent(
        test_client,
        _create_enrollment_token(test_client, admin_headers)["token"],
    )
    agent = _get_agent(test_db, registered["agent_id"])
    headers = _agent_headers(registered["agent_token"])
    repository = Repository(
        name="requeued-prune", path="/requeued-prune", borg_version=1
    )
    test_db.add(repository)
    test_db.commit()
    backups = {
        name: seed_job_operation(
            test_db,
            "backup",
            repository_id=repository.id,
            status="completed",
            archive_name=name,
            created_at=_now_utc() - timedelta(days=3),
        )
        for name in ("host-first", "host-retry", "host-kept")
    }
    prune = seed_job_operation(
        test_db, "prune", repository_id=repository.id, status="running"
    )
    test_db.commit()
    job = agent_maintenance_job(
        test_db, agent, "prune", prune.id, repository=repository
    )
    _make_stale(test_db, job)
    first_run = [
        "Starting prune",
        "Pruning archive (1/2): host-first  Wed, 2026-07-22 18:33:12 [aa]",
        "Keeping archive (rule: daily #1): host-kept  Wed, 2026-07-22 18:00:00 [cc]",
    ]
    _store_lines(test_db, job, first_run, stream="stderr")

    _heartbeat(test_client, registered, headers)
    test_db.refresh(job)
    assert job.status == "queued"

    retry = [
        "Starting prune",
        "Pruning archive (1/1): host-retry  Wed, 2026-07-22 18:40:00 [bb]",
    ]
    _rerun(test_client, job, headers, retry, stream="stderr")
    completed = test_client.post(
        f"/api/agents/jobs/{job.id}/complete",
        json={"result": {"return_code": 0}},
        headers=headers,
    )
    assert completed.status_code == 200

    test_db.expire_all()
    operation = test_db.get(Operation, prune.id)
    assert operation.status == "completed"
    stored = Path(operation.log_file_path).read_text(encoding="utf-8")
    assert stored == "\n".join([first_run[1], REQUEUED_JOB_LOG_MESSAGE, *retry])
    pruned_at = {
        name: test_db.get(OperationBackupDetails, backup.id).archive_pruned_at
        for name, backup in backups.items()
    }
    assert pruned_at["host-first"] is not None
    assert pruned_at["host-retry"] is not None
    assert pruned_at["host-kept"] is None


def _create_agent(db):
    agent = AgentMachine(
        name="Retry Agent",
        agent_id="agt_retry",
        token_hash=get_password_hash("secret"),
        token_prefix="secret",
        status="online",
        capabilities=[],
    )
    db.add(agent)
    db.commit()
    db.refresh(agent)
    return agent


def _create_job(db, agent, *, status="running", started=True, payload=None):
    at = _now_utc() - timedelta(seconds=5)
    job = AgentJob(
        agent_machine_id=agent.id,
        job_type="backup",
        status=status,
        payload=payload or {},
        claimed_at=at,
        started_at=at if started else None,
        created_at=at,
        updated_at=at,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def _requeue_at_hello(db, agent):
    _requeue_stale_agent_jobs(
        db,
        agent,
        now=_now_utc(),
        running_job_ids=[],
        at_hello=True,
        running_job_ids_complete=True,
    )
    db.commit()


def _rows(db, job):
    return [
        (row.sequence, row.message)
        for row in db.query(AgentJobLog)
        .filter(AgentJobLog.agent_job_id == job.id)
        .order_by(AgentJobLog.sequence)
    ]


@pytest.mark.unit
def test_hello_requeue_keeps_the_retrys_session_lines(db_session):
    # An agent process restarted while the job ran: hello requeues the job
    # whatever its age (#1363), and the retry streams its lines over the
    # session from sequence 0 again.
    agent = _create_agent(db_session)
    job = _create_job(db_session, agent)
    _store_lines(db_session, job, FIRST_RUN)

    _requeue_at_hello(db_session, agent)
    db_session.refresh(job)
    assert job.status == "queued"

    for sequence, message in enumerate(RETRY):
        assert _append_agent_job_log(
            job, db_session, sequence=sequence, stream="stdout", message=message
        )
        db_session.commit()

    assert _collect_agent_logs(job, db_session) == REQUEUED_LOG


@pytest.mark.unit
def test_a_second_requeue_leaves_one_note_and_no_earlier_lines(db_session):
    agent = _create_agent(db_session)
    job = _create_job(db_session, agent)
    _store_lines(db_session, job, FIRST_RUN)
    _requeue_at_hello(db_session, agent)

    db_session.refresh(job)
    job.status = "running"
    job.claimed_at = job.started_at = _now_utc()
    db_session.commit()
    _store_lines(db_session, job, RETRY)
    _requeue_at_hello(db_session, agent)

    assert _rows(db_session, job) == [
        (REQUEUED_JOB_LOG_SEQUENCE, REQUEUED_JOB_LOG_MESSAGE)
    ]


@pytest.mark.unit
def test_a_requeued_job_that_logged_nothing_gets_no_note(db_session):
    # An undelivered job never ran; there is nothing to say about a run.
    agent = _create_agent(db_session)
    job = _create_job(db_session, agent, status="claimed", started=False)

    _requeue_at_hello(db_session, agent)
    db_session.refresh(job)

    assert job.status == "queued"
    assert _rows(db_session, job) == []


@pytest.mark.unit
@pytest.mark.parametrize(
    ("status", "payload", "settled_as"),
    [
        # no requeue: the run's lines are the record of how it ended
        ("cancel_requested", {}, "canceled"),
        ("running", {"job_kind": "repository.info"}, "failed"),
    ],
)
def test_a_job_settled_instead_of_requeued_keeps_its_lines(
    db_session, status, payload, settled_as
):
    agent = _create_agent(db_session)
    job = _create_job(db_session, agent, status=status, payload=payload)
    if payload:
        job.job_type = "repository"
        db_session.commit()
    _store_lines(db_session, job, FIRST_RUN)

    _requeue_at_hello(db_session, agent)
    db_session.refresh(job)

    assert job.status == settled_as
    assert _collect_agent_logs(job, db_session) == "\n".join(FIRST_RUN)


@pytest.mark.unit
def test_a_job_the_agent_still_runs_keeps_its_lines(db_session):
    agent = _create_agent(db_session)
    job = _create_job(db_session, agent)
    _store_lines(db_session, job, FIRST_RUN)

    _requeue_stale_agent_jobs(
        db_session,
        agent,
        now=_now_utc(),
        running_job_ids=[job.id],
        at_hello=True,
        running_job_ids_complete=True,
    )
    db_session.commit()
    db_session.refresh(job)

    assert job.status == "running"
    assert _collect_agent_logs(job, db_session) == "\n".join(FIRST_RUN)


@pytest.mark.unit
def test_the_requeue_note_is_not_taken_for_borgs_reason(db_session):
    # An agent before 0.1.10 sends no stderr tail, and the reason is read
    # back from the newest log rows. A retry that failed before its first
    # line leaves only the note, which says nothing about why it failed.
    agent = _create_agent(db_session)
    job = _create_job(db_session, agent)
    _store_lines(db_session, job, FIRST_RUN)
    _requeue_at_hello(db_session, agent)
    db_session.refresh(job)
    job.status = "failed"
    job.error_message = "Agent job exited with code 2"
    job.result = {"return_code": 2}
    db_session.commit()

    assert _agent_job_failure_message(db_session, job) == "Agent job exited with code 2"


@pytest.mark.unit
def test_a_prune_requeued_twice_keeps_the_removed_archives_of_both_runs(
    db_session,
):
    agent = _create_agent(db_session)
    job = _create_job(db_session, agent, payload={"job_kind": "repository.prune"})
    job.job_type = "repository"
    db_session.commit()
    first = "Pruning archive (1/3): host-a  Wed, 2026-07-22 18:33:12 [aa]"
    second = "Pruning archive (1/2): host-b  Wed, 2026-07-22 18:40:00 [bb]"
    # A row may carry more than one line; only the line naming the archive
    # is kept.
    _store_lines(db_session, job, ["Starting prune", f"{first}\ncut off"])
    _requeue_at_hello(db_session, agent)

    db_session.refresh(job)
    job.status = "running"
    job.claimed_at = job.started_at = _now_utc()
    db_session.commit()
    _store_lines(db_session, job, ["Starting prune", second])
    _requeue_at_hello(db_session, agent)

    assert _rows(db_session, job) == [
        (-3, first),
        (-2, second),
        (REQUEUED_JOB_LOG_SEQUENCE, REQUEUED_JOB_LOG_MESSAGE),
    ]
