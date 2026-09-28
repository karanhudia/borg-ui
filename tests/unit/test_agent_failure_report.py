"""An agent failure carries Borg's reason in its own report, and a lock held
by another process defers runner-driven work instead of failing it (#1056)."""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from agent.borg_ui_agent.failure_report import failure_kind
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

LOCK_LINE = "Failed to create/acquire the lock /repo/lock.exclusive (timeout)."


@pytest.fixture()
def session_factory():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_conn, record):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


@pytest.fixture()
def db(session_factory):
    s = session_factory()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture()
def agent(db):
    machine = AgentMachine(
        name="a",
        agent_id="agent-1",
        token_hash="x",
        token_prefix="borgui_agent_x",
        status="online",
    )
    db.add(machine)
    db.add(SystemSettings())
    db.commit()
    return machine


def _repo(db, borg_version):
    r = Repository(
        name=f"r{borg_version}",
        path=f"/tmp/r{borg_version}",
        encryption="none",
        compression="lz4",
        borg_version=borg_version,
        executor_type="agent",
        execution_target="agent",
    )
    db.add(r)
    db.commit()
    return r


@pytest.fixture()
def runner(session_factory, monkeypatch, tmp_path):
    monkeypatch.setattr("app.config.settings.data_dir", str(tmp_path))
    executors.load_default_executors()
    return OperationRunner(
        session_factory=session_factory,
        registry=executors.REGISTRY,
        poll_interval=0.01,
        deferral_delay=0.0,
    )


async def _run_once(runner):
    await runner.tick()
    await asyncio.gather(*list(runner.running_tasks.values()), return_exceptions=True)


def _failed_listing_job(db, agent, repository, *, return_code, stderr_tail):
    """The agent job of a listing the agent reported failed, before any of its
    log lines arrived: the report alone carries what Borg said."""
    now = datetime.now(timezone.utc)
    job = AgentJob(
        agent_machine_id=agent.id,
        job_type="repository",
        status="running",
        payload={
            "schema_version": 1,
            "job_kind": "repository.list_archives",
            "repository": {"id": repository.id},
        },
        created_at=now,
        updated_at=now,
    )
    db.add(job)
    db.commit()
    from app.api.agents import _fail_agent_job

    # the agent's report: the tail and its classification, or neither
    report = (
        {
            "stderr_tail": stderr_tail,
            "failure_kind": failure_kind(return_code, stderr_tail),
        }
        if stderr_tail is not None
        else {}
    )
    _fail_agent_job(
        job,
        db,
        error_message=f"repository.list_archives exited with code {return_code}",
        return_code=return_code,
        **report,
    )
    db.commit()
    return job


@pytest.mark.unit
@pytest.mark.asyncio
async def test_the_failure_message_carries_borgs_reason_without_a_log_line(db, agent):
    """The log line with Borg's reason travels separately and often lands after
    the failure; the reason must come from the failure report itself."""
    from app.services.repository_executor import (
        wait_for_agent_repository_operation_job,
    )

    repository = _repo(db, 1)
    job = _failed_listing_job(
        db, agent, repository, return_code=2, stderr_tail=LOCK_LINE
    )

    with pytest.raises(HTTPException) as excinfo:
        await wait_for_agent_repository_operation_job(
            db, job.id, timeout_seconds=2, poll_interval_seconds=0.01
        )
    assert excinfo.value.detail["params"]["reason"] == (
        f"repository.list_archives exited with code 2: {LOCK_LINE}"
    )


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "borg_version, return_code, stderr_tail",
    [
        # modern exit code (LockTimeout), from an agent that sends no tail
        (2, 73, None),
        (2, 73, LOCK_LINE),
        # legacy exit code (a Borg 1 without the modern setting): the text
        (1, 2, LOCK_LINE),
    ],
)
async def test_a_listing_refused_by_a_foreign_lock_is_deferred(
    db, agent, runner, session_factory, borg_version, return_code, stderr_tail
):
    """A `borg create` started outside Borg UI holds the repository; the
    reconcile's archive_sync must wait for it like for an admission refusal,
    not end failed."""
    repository = _repo(db, borg_version)
    op = enqueue(db, "archive_sync", repository_id=repository.id, trigger="reconcile")

    def _queue(queue_db, repo, **kwargs):
        return _failed_listing_job(
            queue_db,
            agent,
            repo,
            return_code=return_code,
            stderr_tail=stderr_tail,
        )

    with (
        patch(
            "app.services.repository_executor.queue_agent_repository_operation_job",
            side_effect=_queue,
        ),
        patch(
            "app.services.agent_job_dispatcher.dispatch_agent_job_best_effort",
            new=AsyncMock(),
        ),
        patch(
            "app.services.operations.executors.index.archive_end_resolvable",
            return_value=True,
        ),
    ):
        await _run_once(runner)

    db.expire_all()
    row = db.get(Operation, op.id)
    assert row.status == "queued"
    assert row.params["deferrals"] == 1
    assert row.error_message is None


def _failed_agent_job(db, agent, repository, *, return_code, **queue_kwargs):
    """What `queue_agent_repository_operation_job` would have queued, once
    the agent reported it failed on a lock: the payload as the server builds
    it, the caller's deferral flag included."""
    from app.api.agents import _fail_agent_job
    from app.services.repository_executor import (
        LOCK_CONTENTION_DEFERS_KEY,
        build_agent_repository_operation_payload,
    )

    payload = build_agent_repository_operation_payload(
        repository,
        queue_kwargs["job_kind"],
        operation=queue_kwargs.get("operation"),
        maintenance_job_kind=queue_kwargs.get("maintenance_job_kind"),
        maintenance_job_id=queue_kwargs.get("maintenance_job_id"),
    )
    if queue_kwargs.get("ignore_queued_operations"):
        payload[LOCK_CONTENTION_DEFERS_KEY] = True
    now = datetime.now(timezone.utc)
    job = AgentJob(
        agent_machine_id=agent.id,
        job_type="repository",
        status="running",
        payload=payload,
        created_at=now,
        updated_at=now,
    )
    db.add(job)
    db.commit()
    _fail_agent_job(
        job,
        db,
        error_message=f"{queue_kwargs['job_kind']} exited with code {return_code}",
        return_code=return_code,
        stderr_tail=LOCK_LINE,
        failure_kind=failure_kind(return_code, LOCK_LINE),
    )
    db.commit()
    return job


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kind, params",
    [
        ("prune", {}),
        ("compact", {}),
        ("check", {}),
        ("delete_archive", {"archive_name": "a1"}),
    ],
)
async def test_a_maintenance_run_that_lost_the_lock_is_deferred(
    db, agent, runner, session_factory, kind, params
):
    """A foreign process holds the repository while the runner's maintenance
    operation runs on the agent; Borg gives up on the lock. The failure
    report leaves the operation row open, and the runner defers it like an
    admission refusal: nothing records the run as failed."""
    repository = _repo(db, 2)
    op = enqueue(
        db, kind, repository_id=repository.id, trigger="followup", params=params
    )

    def _queue(queue_db, repo, **kwargs):
        assert kwargs["ignore_queued_operations"] is True
        return _failed_agent_job(queue_db, agent, repo, return_code=73, **kwargs)

    with (
        patch("app.database.database.SessionLocal", side_effect=session_factory),
        patch(
            "app.services.repository_executor.queue_agent_repository_operation_job",
            side_effect=_queue,
        ),
        patch(
            "app.services.agent_job_dispatcher.dispatch_agent_job_best_effort",
            new=AsyncMock(),
        ),
    ):
        await _run_once(runner)

    db.expire_all()
    row = db.get(Operation, op.id)
    assert row.status == "queued"
    assert row.params["deferrals"] == 1
    assert row.error_message is None
    assert row.completed_at is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_a_lock_held_past_the_deferral_budget_fails_with_borgs_reason(
    db, agent, runner, session_factory
):
    """The deferral is bounded: a repository that never frees up ends in a
    visible failure that says what Borg saw."""
    from app.services.operations.runner import MAX_DEFERRALS

    repository = _repo(db, 2)
    op = enqueue(db, "archive_sync", repository_id=repository.id, trigger="reconcile")
    op.params = {**(op.params or {}), "deferrals": MAX_DEFERRALS}
    db.commit()

    def _queue(queue_db, repo, **kwargs):
        return _failed_listing_job(
            queue_db, agent, repo, return_code=73, stderr_tail=LOCK_LINE
        )

    with (
        patch(
            "app.services.repository_executor.queue_agent_repository_operation_job",
            side_effect=_queue,
        ),
        patch(
            "app.services.agent_job_dispatcher.dispatch_agent_job_best_effort",
            new=AsyncMock(),
        ),
    ):
        await _run_once(runner)

    db.expire_all()
    row = db.get(Operation, op.id)
    assert row.status == "failed"
    assert row.error_message.startswith(
        f"repository still busy after {MAX_DEFERRALS} attempts: "
    )
    assert LOCK_LINE in row.error_message


@pytest.mark.unit
@pytest.mark.asyncio
async def test_an_old_agents_message_is_redacted_and_a_lost_lock_is_no_contention(
    db, agent
):
    """An agent before 0.1.10 sends no report: the reason comes from its raw
    log rows, redacted before it reaches a row or a notification; and its
    exit code 73 is not contention when the rows say Borg lost its own lock."""
    from app.database.models import AgentJobLog
    from app.services.repository_executor import (
        agent_failure_is_lock_contention,
        wait_for_agent_repository_operation_job,
    )

    repository = _repo(db, 2)
    job = _failed_listing_job(db, agent, repository, return_code=73, stderr_tail=None)
    assert agent_failure_is_lock_contention(job, db)

    db.add(
        AgentJobLog(
            agent_job_id=job.id,
            sequence=2,
            stream="stderr",
            message=(
                "Failed to create/acquire the lock ssh://user:s3cret@host/repo"
                "/lock.exclusive (timeout). Our lock was killed by another borg"
                " - there is no safe way to continue."
            ),
            created_at=datetime.utcnow(),
        )
    )
    db.commit()
    assert not agent_failure_is_lock_contention(job, db)

    with pytest.raises(HTTPException) as excinfo:
        await wait_for_agent_repository_operation_job(
            db, job.id, timeout_seconds=2, poll_interval_seconds=0.01
        )
    reason = excinfo.value.detail["params"]["reason"]
    assert "s3cret" not in reason
    assert "ssh://user:***@host/repo" in reason
    assert excinfo.value.detail.get("lock_contention") is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_the_waiter_reports_the_decision_the_failure_report_took(db, agent):
    """For a job whose caller defers, the waiter's mark is the decision the
    report recorded with the job: a log row that lands in between (an old
    agent's lost-lock line) must not make the two disagree, or the row
    left open by the report would be recorded as failed by the runner."""
    from app.database.models import AgentJobLog
    from app.services.repository_executor import (
        LOCK_CONTENTION_DEFERS_KEY,
        wait_for_agent_repository_operation_job,
    )

    repository = _repo(db, 2)
    job = _failed_agent_job(
        db,
        agent,
        repository,
        return_code=73,
        job_kind="repository.check",
        maintenance_job_kind="check",
        maintenance_job_id=1,
        ignore_queued_operations=True,
    )
    assert job.payload[LOCK_CONTENTION_DEFERS_KEY] is True
    assert job.result["deferred"] is True
    db.add(
        AgentJobLog(
            agent_job_id=job.id,
            sequence=2,
            stream="stderr",
            message="Our lock was killed by another borg",
            created_at=datetime.utcnow(),
        )
    )
    db.commit()

    with pytest.raises(HTTPException) as excinfo:
        await wait_for_agent_repository_operation_job(
            db, job.id, timeout_seconds=2, poll_interval_seconds=0.01
        )
    assert excinfo.value.detail["lock_contention"] is True


@pytest.mark.unit
def test_the_reason_skips_the_show_rc_line():
    """`--show-rc` ends Borg's output with its exit code, which only repeats
    what the message already says; the reason is the line before it."""
    from app.services.repository_executor import _tail_reason_line

    tail = "Repository /repo does not exist.\nterminating with error status, rc 2"
    assert _tail_reason_line(tail, lock_contention=False) == (
        "Repository /repo does not exist."
    )
    assert (
        _tail_reason_line("terminating with error status, rc 2", lock_contention=False)
        is None
    )
    # a lock line before the status line is found through it
    assert (
        _tail_reason_line(
            f"{LOCK_LINE}\nterminating with error status, rc 73", lock_contention=True
        )
        == LOCK_LINE
    )


@pytest.mark.unit
def test_the_reason_precedes_a_traceback():
    """Borg prints its reason first and, for some errors, a traceback and
    its platform block after it; the reason is not the platform block."""
    from app.services.repository_executor import _tail_reason_line

    tail = (
        "Failed to create/acquire the lock /repo/lock.exclusive (Permission denied).\n"
        "Traceback (most recent call last):\n"
        '  File "borg/archiver.py", line 1, in main\n'
        "PermissionError: [Errno 13] Permission denied\n"
        "\n"
        "Platform: Linux host 6.1.0 x86_64\n"
        "Borg: 1.4.1  Python: CPython 3.11.2 msgpack: 1.0.5\n"
        "PID: 4242  CWD: /\n"
        "terminating with error status, rc 2"
    )
    assert _tail_reason_line(tail, lock_contention=False) == (
        "Failed to create/acquire the lock /repo/lock.exclusive (Permission denied)."
    )
    # a traceback with nothing before it: the last line is all there is
    assert (
        _tail_reason_line(
            "Traceback (most recent call last):\nKeyError: 'x'", lock_contention=False
        )
        == "KeyError: 'x'"
    )


@pytest.mark.unit
def test_an_unflagged_or_ordinary_failure_does_not_defer(db, agent):
    """Only a lock failure of a job whose caller asked for the deferral leaves
    its row open: a route's job, or any other failure, is recorded."""
    from types import SimpleNamespace

    from app.services.repository_executor import (
        LOCK_CONTENTION_DEFERS_KEY,
        agent_failure_is_lock_contention,
        lock_contention_defers,
    )

    def job(payload, result):
        return SimpleNamespace(payload=payload, result=result)

    flagged = {LOCK_CONTENTION_DEFERS_KEY: True}
    # the report's classification decides, whatever the exit code
    assert lock_contention_defers(job(flagged, {"failure_kind": "lock_contention"}))
    assert not lock_contention_defers(
        job(flagged, {"return_code": 73, "failure_kind": "other"})
    )
    # an agent that sent no classification: Borg's modern exit code
    assert lock_contention_defers(job(flagged, {"return_code": 73}))
    assert not lock_contention_defers(job(flagged, {"return_code": 2}))
    assert not lock_contention_defers(job(flagged, {"return_code": 74}))
    # a lock file that cannot be created is not held by anyone
    assert not lock_contention_defers(job(flagged, {"return_code": 72}))
    # a job nobody defers for
    assert not lock_contention_defers(job({}, {"return_code": 73}))
    assert agent_failure_is_lock_contention(job({}, {"return_code": 73}))
    assert not lock_contention_defers(job(None, None))
