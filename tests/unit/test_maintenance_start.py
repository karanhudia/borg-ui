"""Phase 5: maintenance work is enqueued, not dispatched."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.database.models import Base, Operation, Repository, utc_now
from tests.utils.agent_jobs import agent_maintenance_job
from app.services.operations.maintenance_start import (
    active_maintenance_operation,
    start_maintenance,
)


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_conn, record):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def repository(db):
    repo = Repository(name="nas", path="/repo/nas", borg_version=1)
    db.add(repo)
    db.commit()
    return repo


def test_start_enqueues_a_queued_operation(db, repository):
    op = start_maintenance(
        db,
        repository,
        "check",
        trigger="manual",
        params={"max_duration": 3600, "extra_flags": None},
        user_id=None,
        duplicate_error_key="backend.errors.repo.checkAlreadyRunning",
    )

    assert op.status == "queued"
    assert op.kind == "check"
    assert op.category == "maintenance"
    assert op.trigger == "manual"
    assert op.repository_id == repository.id
    assert op.params["max_duration"] == 3600


def test_start_rejects_a_second_check_on_the_same_repository(db, repository):
    start_maintenance(
        db,
        repository,
        "check",
        trigger="manual",
        params={},
        user_id=None,
        duplicate_error_key="backend.errors.repo.checkAlreadyRunning",
    )

    with pytest.raises(HTTPException) as excinfo:
        start_maintenance(
            db,
            repository,
            "check",
            trigger="manual",
            params={},
            user_id=None,
            duplicate_error_key="backend.errors.repo.checkAlreadyRunning",
        )

    assert excinfo.value.status_code == 409
    assert excinfo.value.detail["key"] == "backend.errors.repo.checkAlreadyRunning"


def test_start_allows_a_different_kind_to_queue_alongside(db, repository):
    start_maintenance(
        db,
        repository,
        "check",
        trigger="manual",
        params={},
        user_id=None,
        duplicate_error_key="backend.errors.repo.checkAlreadyRunning",
    )

    prune = start_maintenance(
        db,
        repository,
        "prune",
        trigger="manual",
        params={},
        user_id=None,
        duplicate_error_key="backend.errors.repo.pruneAlreadyRunning",
    )

    assert prune.status == "queued"


def test_start_allows_a_new_run_once_the_last_one_finished(db, repository):
    first = start_maintenance(
        db,
        repository,
        "check",
        trigger="manual",
        params={},
        user_id=None,
        duplicate_error_key="backend.errors.repo.checkAlreadyRunning",
    )
    first.status = "completed"
    db.commit()

    second = start_maintenance(
        db,
        repository,
        "check",
        trigger="manual",
        params={},
        user_id=None,
        duplicate_error_key="backend.errors.repo.checkAlreadyRunning",
    )

    assert second.id != first.id


def test_active_maintenance_operation_finds_queued_and_running(db, repository):
    op = start_maintenance(
        db,
        repository,
        "check",
        trigger="schedule",
        params={},
        user_id=None,
        duplicate_error_key="backend.errors.repo.checkAlreadyRunning",
    )

    assert active_maintenance_operation(db, repository.id, "check").id == op.id

    op.status = "running"
    db.commit()
    assert active_maintenance_operation(db, repository.id, "check").id == op.id

    op.status = "failed"
    db.commit()
    assert active_maintenance_operation(db, repository.id, "check") is None


def test_params_drop_none_values(db, repository):
    op = start_maintenance(
        db,
        repository,
        "check",
        trigger="manual",
        params={"max_duration": None, "extra_flags": "--verify-data"},
        user_id=None,
        duplicate_error_key="backend.errors.repo.checkAlreadyRunning",
    )

    assert "max_duration" not in op.params
    assert op.params["extra_flags"] == "--verify-data"


def test_a_scheduled_check_carries_the_schedule_trigger(db, repository):
    op = start_maintenance(
        db,
        repository,
        "check",
        trigger="schedule",
        params={"scheduled_check": True},
        user_id=None,
        duplicate_error_key="backend.errors.repo.checkAlreadyRunning",
    )

    assert op.trigger == "schedule"
    # Spec 6.3: schedule runs at priority 5, behind manual work.
    assert op.priority == 5


def test_start_refuses_a_kind_that_is_not_maintenance(db, repository):
    with pytest.raises(ValueError):
        start_maintenance(
            db,
            repository,
            "backup",
            trigger="manual",
            params={},
            user_id=None,
            duplicate_error_key="backend.errors.repo.checkAlreadyRunning",
        )


def test_inline_maintenance_starts_running_so_the_runner_leaves_it_alone(
    db, repository
):
    from app.services.operations.maintenance_start import start_inline_maintenance

    op = start_inline_maintenance(
        db, repository, "prune", params={"dry_run": True}, user_id=None
    )

    # Spec 7.1 dispatches queued rows only, so an inline row is never picked up.
    assert op.status == "running"
    # no start yet: the service's `claim_running` records it (see the
    # claimability test below)
    assert op.started_at is None


def test_start_inline_maintenance_can_join_a_run(db, repository):
    from app.services.operations.maintenance_start import start_inline_maintenance

    parent = Operation(
        repository_id=repository.id,
        kind="backup",
        category="backup",
        status="completed",
        trigger="plan",
        priority=0,
        run_id="run-9",
    )
    db.add(parent)
    db.commit()

    child = start_inline_maintenance(
        db,
        repository,
        "prune",
        params={},
        user_id=None,
        run_id="run-9",
        depends_on_id=parent.id,
    )

    assert child.run_id == "run-9"
    assert child.depends_on_id == parent.id
    assert child.status == "running"
    # A step of a plan run is plan work, not a manual prune.
    assert child.trigger == "plan"


def test_start_inline_maintenance_inherits_the_schedule_from_its_parent(db, repository):
    from app.services.operations.maintenance_start import start_inline_maintenance

    from app.database.models import ScheduledJob

    schedule = ScheduledJob(name="nightly", cron_expression="0 2 * * *")
    db.add(schedule)
    db.commit()
    parent = Operation(
        repository_id=repository.id,
        kind="backup",
        category="backup",
        status="completed",
        trigger="schedule",
        priority=0,
        run_id="run-10",
        scheduled_job_id=schedule.id,
    )
    db.add(parent)
    db.commit()

    child = start_inline_maintenance(
        db,
        repository,
        "compact",
        params={},
        user_id=None,
        run_id="run-10",
        depends_on_id=parent.id,
    )
    assert child.trigger == "schedule"
    assert child.scheduled_job_id == schedule.id


def test_start_inline_maintenance_alone_is_manual(db, repository):
    from app.services.operations.maintenance_start import start_inline_maintenance

    op = start_inline_maintenance(db, repository, "prune", params={}, user_id=None)
    assert op.trigger == "manual"


def test_finish_inline_enqueues_the_followup_chain(db, repository):
    from app.services.operations.executors import load_default_executors
    from app.services.operations.maintenance_start import (
        finish_inline_maintenance,
        start_inline_maintenance,
    )

    load_default_executors()

    op = start_inline_maintenance(
        db, repository, "prune", params={"keep_daily": 7}, user_id=None
    )
    op.status = "completed"
    db.commit()

    finish_inline_maintenance(db, op)

    followups = (
        db.query(Operation)
        .filter(Operation.depends_on_id.isnot(None), Operation.run_id == op.run_id)
        .order_by(Operation.id.asc())
        .all()
    )
    # Spec 7.4: prune is followed by archive_sync, history_merge, stats.
    # history_merge is not plan gated (only history_index is), so the chain is
    # the same on Community.
    assert [f.kind for f in followups] == ["archive_sync", "history_merge", "stats"]
    assert all(f.trigger == "followup" for f in followups)


def test_finish_inline_enqueues_nothing_after_a_failure(db, repository):
    from app.services.operations.maintenance_start import (
        finish_inline_maintenance,
        start_inline_maintenance,
    )

    op = start_inline_maintenance(db, repository, "prune", params={}, user_id=None)
    op.status = "failed"
    db.commit()

    finish_inline_maintenance(db, op)

    assert db.query(Operation).count() == 1


def test_finish_inline_skips_the_chain_when_asked(db, repository):
    from app.services.operations.maintenance_start import (
        finish_inline_maintenance,
        start_inline_maintenance,
    )

    op = start_inline_maintenance(
        db, repository, "prune", params={"dry_run": True}, user_id=None
    )
    op.status = "completed"
    db.commit()

    finish_inline_maintenance(db, op, enqueue_followups=False)

    assert db.query(Operation).count() == 1


def test_active_delete_is_scoped_to_one_archive(db, repository):
    from app.services.operations.enqueue import enqueue
    from app.services.operations.maintenance_start import active_delete_for_archive

    enqueue(
        db,
        "delete_archive",
        repository_id=repository.id,
        trigger="manual",
        params={"archive_name": "nightly-1"},
    )

    assert active_delete_for_archive(db, repository.id, "nightly-1") is not None
    assert active_delete_for_archive(db, repository.id, "nightly-2") is None


async def test_fail_inline_closes_a_running_operation_with_the_cause(db, repository):
    from app.services.operations.maintenance_start import (
        fail_inline_maintenance,
        start_inline_maintenance,
    )

    op = start_inline_maintenance(db, repository, "prune", params={}, user_id=None)
    assert op.status == "running"

    assert await fail_inline_maintenance(
        db, op, RuntimeError("agent prune failed: refused")
    )

    db.expire_all()
    stored = db.get(Operation, op.id)
    assert stored.status == "failed"
    assert stored.error_message == "agent prune failed: refused"
    assert stored.completed_at is not None


async def test_fail_inline_keeps_a_terminal_status_the_step_already_wrote(
    db, repository
):
    """The agent path fails the operation itself when its job is refused; the
    caller's handler must not overwrite that (or a completion that raced the
    exception) with its own message."""
    from app.services.operations.maintenance_start import (
        fail_inline_maintenance,
        start_inline_maintenance,
    )

    op = start_inline_maintenance(db, repository, "compact", params={}, user_id=None)
    op.status = "completed"
    op.completed_at = utc_now()
    db.commit()

    assert not await fail_inline_maintenance(db, op, RuntimeError("late failure"))

    db.expire_all()
    stored = db.get(Operation, op.id)
    assert stored.status == "completed"
    assert stored.error_message is None


async def test_fail_inline_keeps_an_operation_a_live_agent_job_is_carrying(
    db, repository
):
    """The caller's wait can give up (504) on a prune the agent is still
    running. Failing the row then would free the repository for the next
    step while the agent still holds it; the agent's report closes it."""
    from app.core.security import get_password_hash
    from app.database.models import AgentMachine
    from app.services.operations.maintenance_start import (
        fail_inline_maintenance,
        start_inline_maintenance,
    )

    agent = AgentMachine(
        name="Agent",
        agent_id="agt_inline_live",
        token_hash=get_password_hash("secret"),
        token_prefix="secret",
        status="online",
    )
    db.add(agent)
    db.commit()
    op = start_inline_maintenance(db, repository, "prune", params={}, user_id=None)
    agent_maintenance_job(db, agent, "prune", op.id)

    assert not await fail_inline_maintenance(
        db, op, RuntimeError("agent prune failed: repositoryOperationTimeout")
    )

    db.expire_all()
    assert db.get(Operation, op.id).status == "running"


async def test_fail_inline_recovers_a_session_the_failure_left_unusable(db, repository):
    """The failure that brings the caller here may have doomed its
    transaction (a failed flush stands in for a locked database); the row
    must still be closed, or it blocks the repository until a restart."""
    from sqlalchemy.exc import IntegrityError

    from app.services.operations.maintenance_start import (
        fail_inline_maintenance,
        start_inline_maintenance,
    )

    op = start_inline_maintenance(db, repository, "check", params={}, user_id=None)
    with pytest.raises(IntegrityError):
        db.add(Operation(category="maintenance", run_id="doomed"))
        db.flush()  # kind is NOT NULL

    assert await fail_inline_maintenance(db, op, RuntimeError("database is locked"))

    db.expire_all()
    stored = db.get(Operation, op.id)
    assert stored.status == "failed"
    assert stored.error_message == "database is locked"


async def test_fail_inline_retries_a_locked_commit_with_the_write(db, repository):
    """A locked database is one of the failures that bring a caller here;
    the retry helper rolls back between attempts, so the close must be
    re-issued on each one rather than written once as attributes."""
    from sqlalchemy.exc import OperationalError

    from app.services.operations.maintenance_start import (
        fail_inline_maintenance,
        start_inline_maintenance,
    )

    op = start_inline_maintenance(db, repository, "prune", params={}, user_id=None)
    real_commit = db.commit
    attempts = []

    def flaky_commit():
        attempts.append(1)
        if len(attempts) == 1:
            raise OperationalError(
                "UPDATE operations", {}, Exception("database is locked")
            )
        real_commit()

    with (
        patch.object(db, "commit", side_effect=flaky_commit),
        patch("app.utils.db_retries.asyncio.sleep", new=AsyncMock()),
    ):
        assert await fail_inline_maintenance(db, op, RuntimeError("refused"))

    assert len(attempts) == 2
    db.expire_all()
    stored = db.get(Operation, op.id)
    assert stored.status == "failed"
    assert stored.error_message == "refused"


async def test_fail_inline_gives_up_after_the_retries_and_says_so(db, repository):
    """When every commit attempt hits the lock, the row cannot be closed from
    this session; the caller learns that from the return value (and the
    warning), rather than from a `running` row it believes it closed."""
    from sqlalchemy.exc import OperationalError

    from app.services.operations.maintenance_start import (
        fail_inline_maintenance,
        start_inline_maintenance,
    )

    op = start_inline_maintenance(db, repository, "prune", params={}, user_id=None)

    def locked_commit():
        raise OperationalError("UPDATE operations", {}, Exception("database is locked"))

    with (
        patch.object(db, "commit", side_effect=locked_commit),
        patch("app.utils.db_retries.asyncio.sleep", new=AsyncMock()),
    ):
        assert not await fail_inline_maintenance(db, op, RuntimeError("refused"))

    db.expire_all()
    assert db.get(Operation, op.id).status == "running"


def test_finish_inline_closes_a_row_the_step_returned_without_a_verdict(db, repository):
    """A service that returns with the operation still `running` is a bug in
    the service; the row must not stay `running` for it."""
    from app.services.operations.maintenance_start import (
        finish_inline_maintenance,
        start_inline_maintenance,
    )

    op = start_inline_maintenance(db, repository, "compact", params={}, user_id=None)

    finish_inline_maintenance(db, op)

    db.expire_all()
    stored = db.get(Operation, op.id)
    assert stored.status == "failed"
    assert stored.error_message == "the service returned without recording a verdict"
    assert stored.completed_at is not None
    assert db.query(Operation).filter(Operation.kind != "compact").count() == 0


async def test_fail_inline_keeps_an_operation_a_queued_agent_job_is_waiting_on(
    db, repository
):
    """A queued agent job holds the repository through admission on its own
    and runs on the agent's next hello; the row must agree with the job
    rather than read `failed` while the prune is still going to happen."""
    from app.core.security import get_password_hash
    from app.database.models import AgentMachine
    from app.services.operations.maintenance_start import (
        fail_inline_maintenance,
        start_inline_maintenance,
    )

    agent = AgentMachine(
        name="Agent",
        agent_id="agt_inline_queued",
        token_hash=get_password_hash("secret"),
        token_prefix="secret",
        status="offline",
    )
    db.add(agent)
    db.commit()
    op = start_inline_maintenance(db, repository, "prune", params={}, user_id=None)
    agent_maintenance_job(db, agent, "prune", op.id, status="queued")

    assert not await fail_inline_maintenance(
        db, op, RuntimeError("agent prune failed: repositoryOperationTimeout")
    )

    db.expire_all()
    assert db.get(Operation, op.id).status == "running"


def test_start_inline_records_the_executor(db):
    from app.services.operations.maintenance_start import start_inline_maintenance

    server = Repository(name="server", path="/repo/server", borg_version=1)
    agent = Repository(
        name="agent",
        path="/repo/agent",
        borg_version=1,
        executor_type="agent",
        execution_target="agent",
    )
    db.add_all([server, agent])
    db.commit()

    on_server = start_inline_maintenance(db, server, "prune", params={}, user_id=None)
    on_agent = start_inline_maintenance(db, agent, "prune", params={}, user_id=None)

    assert on_server.execution_mode == "server"
    assert on_agent.execution_mode == "agent"


def test_failure_text_keeps_statement_parameters_out():
    """A statement error renders the SQL and its parameters, and the agent
    job insert carries the repository secrets; only the driver's error is
    a message users may read."""
    from sqlalchemy.exc import OperationalError

    from app.services.operations.maintenance_start import failure_text

    error = OperationalError(
        "INSERT INTO agent_jobs (payload)",
        {"payload": '{"secrets": {"BORG_PASSPHRASE": {"value": "hunter2"}}}'},
        Exception("database is locked"),
    )

    assert failure_text(error) == "Exception: database is locked"
    assert failure_text(RuntimeError("agent prune failed")) == "agent prune failed"
    assert failure_text(RuntimeError()) == "RuntimeError"
    # an HTTPException reads as its detail, not as `409: {...}`
    assert (
        failure_text(
            HTTPException(
                status_code=409,
                detail={
                    "key": "backend.errors.jobs.repositoryOperationActive",
                    "params": {"active_operation": "list_archives"},
                },
            )
        )
        == "list_archives is active on the repository"
    )


def test_start_inline_leaves_the_claim_to_the_service(db, repository):
    """The Borg 2 services claim the row through `claim_running` before they
    run and return without running when the claim fails; a `running` row
    with a start already recorded is exactly what they cannot claim."""
    from datetime import datetime, timezone

    from app.services.operations.job_facade import claim_running
    from app.services.operations.maintenance_start import start_inline_maintenance

    op = start_inline_maintenance(db, repository, "prune", params={}, user_id=None)
    assert op.status == "running"
    assert op.started_at is None

    assert claim_running(db, op.id, "prune", datetime.now(timezone.utc)) == 1
    db.commit()
    db.expire_all()
    assert db.get(Operation, op.id).started_at is not None


def test_finish_inline_swallows_a_failed_close_and_leaves_the_row(db, repository):
    """The close must never raise past the caller (the plan calls it outside
    its handler); a locked database leaves the row for the next writer."""
    from sqlalchemy.exc import OperationalError

    from app.services.operations.maintenance_start import (
        finish_inline_maintenance,
        start_inline_maintenance,
    )

    op = start_inline_maintenance(db, repository, "check", params={}, user_id=None)

    def locked():
        raise OperationalError("UPDATE operations", {}, Exception("database is locked"))

    with patch.object(db, "commit", side_effect=locked):
        finish_inline_maintenance(db, op)

    db.expire_all()
    assert db.get(Operation, op.id).status == "running"
