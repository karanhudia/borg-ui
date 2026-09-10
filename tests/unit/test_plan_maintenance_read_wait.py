"""The plan's maintenance step waits out transient read work instead of
failing on it.

A backup's index follow-up lists the repository within a second of the
backup finishing, which is when a plan asks for its prune or compact.
Admission refuses the write; the plan side now waits for the listing to
finish and asks again, bounded, symmetric to the runner's deferral.
"""

import asyncio
import inspect
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

import app.core.borg_router as borg_router_module
from app.core.borg_router import BorgRouter
from app.core.security import get_password_hash
from app.database.models import AgentJob, AgentMachine, Operation, Repository
from app.services.job_admission import (
    OPERATION_CLASS_REPOSITORY_READ,
    READ_WORK_BLOCKED,
    READ_WORK_CANCELLED,
    READ_WORK_CLEARED,
    READ_WORK_TIMEOUT,
    READ_WORK_UNCLAIMED,
    OPERATION_CLASS_REPOSITORY_WRITE,
    OPERATION_PRUNE,
    REPOSITORY_OPERATION_ACTIVE_KEY,
    ensure_repository_admission,
    refused_by_transient_read_work,
    wait_for_transient_read_work,
)


def _refusal(
    active_class: str = OPERATION_CLASS_REPOSITORY_READ,
    *,
    requested: str = "prune",
    active: str = "repository.list_archives",
    key: str = REPOSITORY_OPERATION_ACTIVE_KEY,
) -> HTTPException:
    """A refusal shaped like `_conflict_detail` builds it (the real shape is
    exercised against admission below)."""
    return HTTPException(
        status_code=409,
        detail={
            "key": key,
            "params": {
                "repository_id": 8,
                "repository": "/repos/eight",
                "requested_operation": requested,
                "active_operation": active,
                "active_operation_class": active_class,
                "active_job_table": "agent_jobs",
                "active_job_id": 83482,
                "active_status": "claimed",
            },
        },
    )


def _agent_repository(db_session, name: str):
    agent = AgentMachine(
        name=f"agent-{name}",
        agent_id=f"agt_{name}",
        token_hash=get_password_hash("agent-secret"),
        token_prefix="agent-secret",
        status="online",
    )
    repo = Repository(
        name=name,
        path=f"/repos/{name}",
        encryption="none",
        repository_type="local",
        executor_type="agent",
        agent_machine_id=1,
    )
    db_session.add_all([agent, repo])
    db_session.flush()
    repo.agent_machine_id = agent.id
    db_session.commit()
    return agent, repo


def _agent_job(db_session, agent, repo, *, kind="repository.list_archives"):
    job = AgentJob(
        agent_machine_id=agent.id,
        job_type="repository",
        status="claimed",
        payload={
            "schema_version": 1,
            "job_kind": kind,
            "repository": {"id": repo.id, "path": repo.path},
        },
    )
    db_session.add(job)
    db_session.commit()
    return job


def _operation(db_session, repo, kind, status, *, category="maintenance"):
    op = Operation(
        repository_id=repo.id,
        kind=kind,
        category=category,
        status=status,
        trigger="manual",
        run_id=f"run-{kind}-{status}",
    )
    db_session.add(op)
    db_session.commit()
    return op


# -- the predicate ------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize("active", ["repository.list_archives", "repository.info"])
def test_transient_read_work_in_the_way_is_worth_a_wait(active):
    assert refused_by_transient_read_work(_refusal(active=active))


@pytest.mark.unit
@pytest.mark.parametrize(
    "exc",
    [
        # read class, but long-running, and a queued one cannot start while
        # the caller's own exclusive row is running
        _refusal(active="check"),
        _refusal(active="restore"),
        _refusal(active="repository.list_archive_contents"),
        _refusal(active="repository.rclone_sync"),
        _refusal(OPERATION_CLASS_REPOSITORY_WRITE, active="backup"),
        _refusal(requested="prune", active="prune"),
        _refusal(key="backend.errors.other"),
        HTTPException(status_code=502, detail={"key": REPOSITORY_OPERATION_ACTIVE_KEY}),
        HTTPException(status_code=409, detail="not a dict"),
        HTTPException(status_code=409, detail={"key": REPOSITORY_OPERATION_ACTIVE_KEY}),
        RuntimeError("database is locked"),
    ],
)
def test_every_other_refusal_reaches_the_caller(exc):
    assert not refused_by_transient_read_work(exc)


@pytest.mark.unit
def test_the_predicate_reads_what_admission_actually_raises(db_session):
    # The hand-built refusals above mirror `_conflict_detail`; this pins the
    # predicate to the real shape, against real rows.
    agent, repo = _agent_repository(db_session, "listing-refusal")
    _agent_job(db_session, agent, repo)

    with pytest.raises(HTTPException) as refused_by_listing:
        ensure_repository_admission(db_session, repo, OPERATION_PRUNE)
    assert refused_by_transient_read_work(refused_by_listing.value)

    db_session.rollback()
    db_session.query(AgentJob).delete()
    _operation(db_session, repo, "check", "queued")

    with pytest.raises(HTTPException) as refused_by_check:
        ensure_repository_admission(db_session, repo, OPERATION_PRUNE)
    assert not refused_by_transient_read_work(refused_by_check.value)


# -- the wait, against real rows ------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
async def test_wait_returns_once_the_listing_is_gone(db_session):
    agent, repo = _agent_repository(db_session, "listing")
    job = _agent_job(db_session, agent, repo)

    async def _finish_listing():
        await asyncio.sleep(0.05)
        job.status = "completed"
        db_session.commit()

    finisher = asyncio.ensure_future(_finish_listing())
    cleared = await wait_for_transient_read_work(
        db_session, repo, timeout_seconds=5, poll_interval_seconds=0.01
    )
    await finisher

    assert cleared == READ_WORK_CLEARED


@pytest.mark.unit
@pytest.mark.asyncio
async def test_wait_gives_up_at_once_on_read_work_that_cannot_clear(db_session):
    # A queued check is read class, but it is exclusive and waits for the
    # caller's own running row: waiting for it would burn the whole budget.
    agent, repo = _agent_repository(db_session, "checked")
    _operation(db_session, repo, "check", "queued")

    started = time.monotonic()
    cleared = await wait_for_transient_read_work(
        db_session, repo, timeout_seconds=5, poll_interval_seconds=0.01
    )

    assert cleared == READ_WORK_BLOCKED
    assert time.monotonic() - started < 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_wait_does_not_look_at_write_work(db_session):
    # A write refused by a write never reaches the wait; running write work
    # on its own is not something to wait for.
    agent, repo = _agent_repository(db_session, "writing")
    _operation(db_session, repo, "backup", "running", category="backup")

    assert (
        await wait_for_transient_read_work(
            db_session, repo, timeout_seconds=5, poll_interval_seconds=0.01
        )
        == READ_WORK_CLEARED
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_wait_stops_at_the_timeout_and_on_cancellation(db_session):
    agent, repo = _agent_repository(db_session, "stuck")
    _agent_job(db_session, agent, repo, kind="repository.info")

    started = time.monotonic()
    outcome = await wait_for_transient_read_work(
        db_session, repo, timeout_seconds=0.2, poll_interval_seconds=0.01
    )
    assert outcome == READ_WORK_TIMEOUT
    # it polled until the deadline rather than giving up on the first look
    assert time.monotonic() - started >= 0.2

    assert (
        await wait_for_transient_read_work(
            db_session,
            repo,
            timeout_seconds=5,
            poll_interval_seconds=0.01,
            is_cancelled=lambda: True,
        )
        == READ_WORK_CANCELLED
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_wait_gives_up_on_a_listing_no_agent_ever_claims(db_session):
    # queued is active work for admission, but the reaper never reaps it:
    # past the grace, nothing but queued jobs means the agent is gone
    agent, repo = _agent_repository(db_session, "unclaimed")
    job = _agent_job(db_session, agent, repo)
    job.status = "queued"
    db_session.commit()

    started = time.monotonic()
    outcome = await wait_for_transient_read_work(
        db_session,
        repo,
        timeout_seconds=5,
        poll_interval_seconds=0.01,
        unclaimed_grace_seconds=0.1,
    )
    assert outcome == READ_WORK_UNCLAIMED
    assert 0.1 <= time.monotonic() - started < 2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_the_unclaimed_grace_starts_when_only_queued_jobs_are_left(db_session):
    # a listing that runs for a while and then queues a new job must not
    # use up the new job's grace; the grace counts from the moment nothing
    # but that queued job is left
    agent, repo = _agent_repository(db_session, "grace-restart")
    listing = _agent_job(db_session, agent, repo)

    async def _finish_listing_then_queue_an_info():
        await asyncio.sleep(0.15)
        listing.status = "completed"
        info = _agent_job(db_session, agent, repo, kind="repository.info")
        info.status = "queued"
        db_session.commit()

    switch = asyncio.ensure_future(_finish_listing_then_queue_an_info())
    started = time.monotonic()
    outcome = await wait_for_transient_read_work(
        db_session,
        repo,
        timeout_seconds=5,
        poll_interval_seconds=0.01,
        unclaimed_grace_seconds=0.1,
    )
    await switch

    assert outcome == READ_WORK_UNCLAIMED
    # the claimed phase (0.15 s) plus the queued job's own grace (0.1 s)
    assert time.monotonic() - started >= 0.25


@pytest.mark.unit
@pytest.mark.asyncio
async def test_wait_ends_the_transaction_before_every_poll():
    # The refused admission left the repository row locked in this session,
    # and a poll must not pin a pooled connection idle in a transaction.
    db = MagicMock()
    repository = SimpleNamespace(id=8, path="/repos/eight")
    listing = SimpleNamespace(
        operation="repository.list_archives",
        operation_class=OPERATION_CLASS_REPOSITORY_READ,
        status="claimed",
    )
    listings = [[listing], [listing], []]
    seen_rollbacks: list[int] = []

    def _list(*args, **kwargs):
        seen_rollbacks.append(db.rollback.call_count)
        return listings.pop(0)

    with patch("app.services.job_admission.list_active_repository_work", _list):
        outcome = await wait_for_transient_read_work(
            db, repository, timeout_seconds=5, poll_interval_seconds=0.01
        )
    assert outcome == READ_WORK_CLEARED
    # a rollback before every poll, and one more after the last so the
    # caller's pause afterwards does not sit in a transaction
    assert all(count >= index + 1 for index, count in enumerate(seen_rollbacks))
    assert db.rollback.call_count > seen_rollbacks[-1]


# -- the router: retry loop around the queue call ----------------------------------


class _Router:
    """`_run_agent_maintenance` with the queue call, the wait and the orphan
    helper replaced; the row-closing paths are checked against real rows
    further down."""

    def __init__(
        self, queue_side_effects, *, wait_results=(READ_WORK_CLEARED,), budget=180.0
    ):
        self.db = MagicMock()
        self.db.query.return_value.get.return_value = SimpleNamespace(
            id=8, path="/repos/eight"
        )
        self.db.query.return_value.first.return_value = None
        self.queue = MagicMock(side_effect=list(queue_side_effects))
        self.wait = AsyncMock(side_effect=list(wait_results))
        # the orphan helper is synchronous on main and awaited once #1008
        # lands; the same test must hold on both sides of that merge
        self.abandon = MagicMock(return_value=SimpleNamespace(id=99, status="canceled"))
        self.dispatch = AsyncMock()
        self.fail_orphan = (
            AsyncMock()
            if inspect.iscoroutinefunction(
                borg_router_module._fail_orphaned_maintenance_job
            )
            else MagicMock()
        )
        self.cancel_row = MagicMock()
        self.budget = budget

    async def prune(self, *, wait_for_read_work=True, **kwargs):
        repo = SimpleNamespace(borg_version=1, id=8, executor_type="agent")
        with (
            patch("app.database.database.SessionLocal", return_value=self.db),
            patch(
                "app.services.repository_executor.queue_agent_repository_operation_job",
                self.queue,
            ),
            patch(
                "app.services.agent_job_dispatcher.dispatch_agent_job_best_effort",
                self.dispatch,
            ),
            patch(
                "app.services.agent_job_dispatcher.dispatch_agent_cancel_if_connected",
                new=AsyncMock(),
            ),
            patch(
                "app.services.repository_executor.abandon_agent_repository_operation_job",
                self.abandon,
            ),
            patch(
                "app.services.repository_executor.wait_for_agent_repository_operation_job",
                new=AsyncMock(return_value={}),
            ),
            patch("app.services.job_admission.wait_for_transient_read_work", self.wait),
            patch(
                "app.services.job_admission.TRANSIENT_READ_WAIT_SECONDS", self.budget
            ),
            patch(
                "app.core.borg_router._fail_orphaned_maintenance_job", self.fail_orphan
            ),
            patch(
                "app.core.borg_router._cancel_unqueued_maintenance_job", self.cancel_row
            ),
        ):
            await BorgRouter(repo)._run_agent_maintenance(
                job_kind="repository.prune",
                maintenance_kind="prune",
                maintenance_job_id=9908,
                operation={"keep_daily": 7},
                wait_for_read_work=wait_for_read_work,
                retry_pause_seconds=0.0,
                **kwargs,
            )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_without_opting_in_the_first_refusal_is_the_answer():
    # the runner (which defers on its own), the routes and the schedulers
    # keep the immediate refusal
    router = _Router([_refusal(), SimpleNamespace(id=99)])

    with pytest.raises(RuntimeError, match="agent prune failed"):
        await router.prune(wait_for_read_work=False)

    assert router.queue.call_count == 1
    router.wait.assert_not_awaited()
    router.fail_orphan.assert_called_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_prune_waits_out_the_listing_and_asks_again():
    router = _Router([_refusal(), SimpleNamespace(id=99)])

    await router.prune()

    assert router.queue.call_count == 2
    router.wait.assert_awaited_once()
    kwargs = router.wait.await_args.kwargs
    assert 0 < kwargs["timeout_seconds"] <= 180
    router.fail_orphan.assert_not_called()
    router.cancel_row.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_prune_keeps_asking_while_listings_keep_landing_in_the_gap():
    # history_index queues one archive_info after another; the retry may
    # land in the sub-second gap between two of them and be refused again
    router = _Router(
        [_refusal(), _refusal(active="repository.info"), SimpleNamespace(id=99)],
        wait_results=(READ_WORK_CLEARED, READ_WORK_CLEARED),
    )

    await router.prune()

    assert router.queue.call_count == 3
    assert router.wait.await_count == 2
    router.fail_orphan.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_prune_refused_by_a_write_fails_at_once():
    router = _Router([_refusal(OPERATION_CLASS_REPOSITORY_WRITE, active="backup")])

    with pytest.raises(RuntimeError, match="agent prune failed"):
        await router.prune()

    assert router.queue.call_count == 1
    router.wait.assert_not_awaited()
    router.fail_orphan.assert_called_once()
    assert router.fail_orphan.call_args.args[1:3] == ("prune", 9908)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_prune_gives_up_when_the_read_work_will_not_clear():
    router = _Router([_refusal(), _refusal()], wait_results=(READ_WORK_BLOCKED,))

    with pytest.raises(RuntimeError, match="agent prune failed"):
        await router.prune()

    assert router.queue.call_count == 1
    router.wait.assert_awaited_once()
    router.fail_orphan.assert_called_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_prune_stops_waiting_once_the_budget_is_spent():
    router = _Router([_refusal(), _refusal()], budget=0.0)

    with pytest.raises(RuntimeError, match="agent prune failed"):
        await router.prune()

    assert router.queue.call_count == 1
    router.wait.assert_not_awaited()
    router.fail_orphan.assert_called_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_a_cancelled_run_ends_the_wait_as_cancelled_not_failed():
    router = _Router(
        [_refusal(), SimpleNamespace(id=99)], wait_results=(READ_WORK_CANCELLED,)
    )
    cancelled = iter([False, True])

    # not cancelled when refused, cancelled by the time the wait gives up
    await router.prune(is_cancelled=lambda: next(cancelled, True))

    assert router.queue.call_count == 1
    router.wait.assert_awaited_once()
    router.cancel_row.assert_called_once()
    assert router.cancel_row.call_args.args[1:] == ("prune", 9908)
    router.fail_orphan.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_a_run_already_cancelled_is_never_queued():
    router = _Router([SimpleNamespace(id=99)])

    await router.prune(is_cancelled=lambda: True)

    router.queue.assert_not_called()
    router.wait.assert_not_awaited()
    router.cancel_row.assert_called_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_a_run_cancelled_during_the_pause_is_not_queued_on_the_retry():
    # not cancelled before the first attempt nor right after the wait; the
    # cancel lands during the pause, and the retry's own check catches it
    router = _Router(
        [_refusal(), SimpleNamespace(id=99)], wait_results=(READ_WORK_CLEARED,)
    )
    cancelled = iter([False, False, True])

    await router.prune(is_cancelled=lambda: next(cancelled, True))

    assert router.queue.call_count == 1
    router.wait.assert_awaited_once()
    router.cancel_row.assert_called_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_a_cancel_landing_between_check_and_commit_takes_the_job_back():
    # the check before the attempt saw no cancel; by the time the agent job
    # is committed the run is cancelled: the job is abandoned before any
    # dispatch, and the outcome is a cancellation
    router = _Router([SimpleNamespace(id=99)])
    cancelled = iter([False, True])

    await router.prune(is_cancelled=lambda: next(cancelled, True))

    assert router.queue.call_count == 1
    router.abandon.assert_called_once()
    assert router.abandon.call_args.args[1] == 99
    router.dispatch.assert_not_awaited()
    router.cancel_row.assert_called_once()
    router.fail_orphan.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cancellation_during_the_wait_still_reaches_the_orphan_helper():
    router = _Router([_refusal()], wait_results=(asyncio.CancelledError(),))

    with pytest.raises(asyncio.CancelledError):
        await router.prune()

    router.fail_orphan.assert_called_once()


# -- the rows the router closes itself ------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
async def test_a_cancelled_run_closes_the_operation_row_as_cancelled(db_session):
    # Cancellation is the one outcome this change owns end to end: the row
    # the plan created `running` must read cancelled afterwards, so the
    # plan reports the run as cancelled and nothing blocks the repository.
    agent, repo = _agent_repository(db_session, "cancel-row")
    _agent_job(db_session, agent, repo)
    prune = _operation(db_session, repo, "prune", "running")
    prune_id = prune.id
    router_repo = SimpleNamespace(borg_version=1, id=repo.id, executor_type="agent")

    with (
        patch("app.database.database.SessionLocal", return_value=db_session),
        # capabilities are the agent's business; admission is what matters here
        patch(
            "app.services.repository_executor.validate_agent_repository_operation",
            return_value=agent,
        ),
    ):
        await BorgRouter(router_repo)._run_agent_maintenance(
            job_kind="repository.prune",
            maintenance_kind="prune",
            maintenance_job_id=prune_id,
            operation={"keep_daily": 7},
            is_cancelled=lambda: True,
            wait_for_read_work=True,
        )

    # the router closed the session it was handed; read the row afresh
    row = db_session.get(Operation, prune_id)
    assert row.status == "cancelled"
    assert row.completed_at is not None
    assert "cancelled" in row.error_message


@pytest.mark.unit
@pytest.mark.asyncio
async def test_a_cancelled_row_that_cannot_be_closed_is_not_reported_as_clean():
    # returning normally would leave an active row behind a "cancelled" run
    router = _Router([SimpleNamespace(id=99)])
    router.cancel_row.side_effect = RuntimeError("database is locked")

    with pytest.raises(RuntimeError, match="database is locked"):
        await router.prune(is_cancelled=lambda: True)

    router.queue.assert_not_called()
    router.cancel_row.assert_called_once()


@pytest.mark.unit
def test_the_cancel_helper_logs_and_re_raises_when_the_row_cannot_be_closed():
    from app.core.borg_router import _cancel_unqueued_maintenance_job

    db = MagicMock()
    with (
        patch(
            "app.services.operations.job_facade.resolve_maintenance_job",
            side_effect=RuntimeError("database is locked"),
        ),
        pytest.raises(RuntimeError, match="database is locked"),
    ):
        _cancel_unqueued_maintenance_job(db, "prune", 9908)
    # rolled back before the attempt and again after the failure
    assert db.rollback.call_count == 2
    db.commit.assert_not_called()


# -- the callers hand in their cancel check ----------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["prune", "compact"])
async def test_router_entry_points_forward_the_wait_and_the_cancel_check(method):
    repo = SimpleNamespace(borg_version=1, id=8, executor_type="agent")
    is_cancelled = lambda: False  # noqa: E731
    with patch.object(
        BorgRouter, "_run_agent_maintenance", new=AsyncMock()
    ) as run_agent:
        if method == "prune":
            await BorgRouter(repo).prune(
                1, 0, 7, 4, 6, 0, 1, is_cancelled=is_cancelled, wait_for_read_work=True
            )
        else:
            await BorgRouter(repo).compact(
                1, is_cancelled=is_cancelled, wait_for_read_work=True
            )
    kwargs = run_agent.await_args.kwargs
    assert kwargs["is_cancelled"] is is_cancelled
    assert kwargs["wait_for_read_work"] is True
