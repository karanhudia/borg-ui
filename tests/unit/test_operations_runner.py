import asyncio
import time
from datetime import datetime

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.models import Base, Operation, Repository, SystemSettings
from app.services.operations.enqueue import enqueue, enqueue_chain
from app.services.operations.runner import (
    OperationContext,
    OperationRunner,
    Outcome,
)


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
def repo(db):
    r = Repository(name="r", path="/tmp/r", encryption="none", compression="lz4")
    db.add(r)
    db.add(SystemSettings())
    db.commit()
    return r


@pytest.fixture()
def registry():
    return {}


@pytest.fixture()
def runner(session_factory, registry, monkeypatch, tmp_path):
    monkeypatch.setattr("app.config.settings.data_dir", str(tmp_path))
    return OperationRunner(
        session_factory=session_factory,
        registry=registry,
        poll_interval=0.01,
        deferral_delay=0.0,
    )


async def _drain(runner, rounds=20):
    for _ in range(rounds):
        await runner.tick()
        if runner.running_tasks:
            await asyncio.gather(
                *list(runner.running_tasks.values()), return_exceptions=True
            )
        await asyncio.sleep(0)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_dispatch_order_priority_then_age(db, repo, runner, registry):
    order = []

    async def record(ctx: OperationContext):
        order.append(ctx.operation_id)
        return Outcome()

    registry["stats"] = record
    late_high = enqueue(db, "stats", repository_id=repo.id, priority=20)
    early_low = enqueue(db, "stats", repository_id=repo.id, priority=0)
    await _drain(runner)
    assert order == [early_low.id, late_high.id]
    db.expire_all()
    assert {o.status for o in db.query(Operation)} == {"completed"}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_dependency_gating_and_failure_skips_chain(db, repo, runner, registry):
    async def fail(ctx):
        raise RuntimeError("boom")

    async def ok(ctx):
        return Outcome()

    registry["stats"] = fail
    registry["archive_sync"] = ok
    chain = enqueue_chain(
        db, ["stats", "archive_sync"], repository_id=repo.id, trigger="manual"
    )
    await _drain(runner)
    db.expire_all()
    first, second = (db.get(Operation, c.id) for c in chain)
    assert first.status == "failed"
    assert first.error_message == "boom"
    assert second.status == "skipped"
    assert second.skip_reason == "dependency_failed"
    assert second.completed_at is not None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_dependency_waits_for_success(db, repo, runner, registry):
    seen = []

    async def ok(ctx):
        seen.append(ctx.kind)
        return Outcome()

    registry["stats"] = ok
    registry["archive_sync"] = ok
    enqueue_chain(
        db, ["stats", "archive_sync"], repository_id=repo.id, trigger="manual"
    )
    dispatched = await runner.tick()
    assert dispatched == 1
    await asyncio.gather(*runner.running_tasks.values())
    await runner.tick()
    await asyncio.gather(*runner.running_tasks.values())
    assert seen == ["stats", "archive_sync"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_skipped_dependency_satisfies_dependants(db, repo, runner, registry):
    """A skipped stage is not a failed one: `stats` behind a `history_index`
    that had nothing to do still runs (#917)."""

    async def skip(ctx):
        return Outcome(status="skipped", skip_reason="agent_diff_unsupported")

    async def ok(ctx):
        return Outcome(result={"unique_csize": 1})

    registry["history_index"] = skip
    registry["stats"] = ok
    chain = enqueue_chain(
        db, ["history_index", "stats"], repository_id=repo.id, trigger="reconcile"
    )
    await _drain(runner)
    db.expire_all()
    first, second = (db.get(Operation, c.id) for c in chain)
    assert first.status == "skipped"
    assert first.skip_reason == "agent_diff_unsupported"
    assert second.status == "completed"
    assert second.result == {"unique_csize": 1}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_missing_executor_is_skipped(db, repo, runner, registry):
    op = enqueue(db, "history_index", repository_id=repo.id)
    await runner.tick()
    db.expire_all()
    op = db.get(Operation, op.id)
    assert op.status == "skipped"
    assert op.skip_reason == "executor_unavailable"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_followups_created_on_success_only_for_registered_kinds(
    db, repo, runner, registry
):
    async def ok(ctx):
        return Outcome()

    registry["import_connect"] = ok
    registry["stats"] = ok
    registry["archive_sync"] = ok
    parent = enqueue(db, "import_connect", repository_id=repo.id, trigger="import")
    await _drain(runner)
    db.expire_all()
    rows = db.query(Operation).order_by(Operation.id).all()
    assert [r.kind for r in rows] == ["import_connect", "stats", "archive_sync"]
    assert rows[1].depends_on_id == parent.id
    assert rows[2].depends_on_id == rows[1].id
    assert {r.run_id for r in rows} == {parent.run_id}
    assert rows[1].trigger == "followup" and rows[1].priority == 10
    assert {r.status for r in rows} == {"completed"}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_followups_skip_history_kinds_on_community(
    db, repo, runner, registry, monkeypatch
):
    """A successful backup on a Community install enqueues archive_sync and
    stats but no history_index, even though its executor is registered."""

    async def ok(ctx):
        return Outcome()

    registry["backup"] = ok
    registry["archive_sync"] = ok
    registry["history_index"] = ok
    registry["stats"] = ok

    monkeypatch.setattr(
        "app.services.operations.runner.history_enabled", lambda db: False
    )
    enqueue(db, "backup", repository_id=repo.id, trigger="manual")
    await _drain(runner)
    db.expire_all()
    rows = db.query(Operation).order_by(Operation.id).all()
    assert [r.kind for r in rows] == ["backup", "archive_sync", "stats"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_followups_include_history_kinds_on_pro(
    db, repo, runner, registry, monkeypatch
):
    async def ok(ctx):
        return Outcome()

    registry["backup"] = ok
    registry["archive_sync"] = ok
    registry["history_index"] = ok
    registry["stats"] = ok

    monkeypatch.setattr(
        "app.services.operations.runner.history_enabled", lambda db: True
    )
    enqueue(db, "backup", repository_id=repo.id, trigger="manual")
    await _drain(runner)
    db.expire_all()
    rows = db.query(Operation).order_by(Operation.id).all()
    assert [r.kind for r in rows] == [
        "backup",
        "archive_sync",
        "history_index",
        "stats",
    ]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_no_followups_on_failure(db, repo, runner, registry):
    async def fail(ctx):
        return Outcome(status="failed", error_message="nope")

    registry["import_connect"] = fail
    enqueue(db, "import_connect", repository_id=repo.id, trigger="import")
    await _drain(runner)
    db.expire_all()
    assert db.query(Operation).count() == 1
    assert db.query(Operation).first().error_message == "nope"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_lane_blocks_second_exclusive_until_first_finishes(
    db, repo, runner, registry
):
    gate = asyncio.Event()

    async def wait(ctx):
        await gate.wait()
        return Outcome()

    registry["history_index"] = wait
    enqueue(db, "history_index", repository_id=repo.id)
    enqueue(db, "history_index", repository_id=repo.id)
    assert await runner.tick() == 1
    assert await runner.tick() == 0
    gate.set()
    await asyncio.gather(*runner.running_tasks.values())
    assert await runner.tick() == 1
    await asyncio.gather(*runner.running_tasks.values())


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cancel_queued_and_running(db, repo, runner, registry):
    started = asyncio.Event()

    async def slow(ctx):
        started.set()
        while not ctx.cancelled():
            await asyncio.sleep(0.01)
        return Outcome(status="skipped", skip_reason="cancelled_by_user")

    registry["stats"] = slow
    queued = enqueue(db, "stats", repository_id=repo.id, priority=5)
    running = enqueue(db, "stats", repository_id=repo.id, priority=0)
    await runner.tick()
    await started.wait()
    assert await runner.request_cancel(queued.id) is True
    assert await runner.request_cancel(running.id) is True
    await asyncio.gather(*runner.running_tasks.values(), return_exceptions=True)
    db.expire_all()
    assert db.get(Operation, queued.id).status == "cancelled"
    assert db.get(Operation, running.id).status == "cancelled"
    assert await runner.request_cancel(queued.id) is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cancel_preserves_a_service_written_cancelled_status(
    db, repo, runner, registry
):
    """A maintenance executor's `_run` helper (spec section 13 phase 5)
    writes `cancelled` straight to the row through the legacy job facade,
    since `Outcome` has no cancelled member, and reports the verdict back as
    `Outcome(status="failed", ...)`. `run_operation` must not let that
    outcome overwrite the row's already-correct `cancelled` status with
    `failed`."""
    started = asyncio.Event()

    async def cancels_like_a_maintenance_kind(ctx):
        started.set()
        while not ctx.cancelled():
            await asyncio.sleep(0.01)
        # `ctx.db` is the same session (and identity-mapped Operation
        # instance) `run_operation` holds as `op`, exactly like the real
        # `_run` helper in executors/maintenance.py.
        ctx.operation.status = "cancelled"
        ctx.db.commit()
        return Outcome(status="failed", error_message="cancelled")

    registry["stats"] = cancels_like_a_maintenance_kind
    op = enqueue(db, "stats", repository_id=repo.id)
    await runner.tick()
    await started.wait()
    assert await runner.request_cancel(op.id) is True
    await asyncio.gather(*runner.running_tasks.values(), return_exceptions=True)
    db.expire_all()
    assert db.get(Operation, op.id).status == "cancelled"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cancel_refused_for_running_rows_this_process_does_not_own(
    db, repo, runner
):
    """Rows left running by another worker, or kept by recovery because their
    process is still alive, have no task here to observe the flag."""
    orphan = enqueue(db, "stats", repository_id=repo.id)
    orphan.status = "running"
    db.commit()
    assert await runner.request_cancel(orphan.id) is False
    assert orphan.id not in runner.cancel_requested
    db.expire_all()
    assert db.get(Operation, orphan.id).status == "running"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_progress_and_log(db, repo, runner, registry, tmp_path):
    async def work(ctx):
        ctx.log("hello")
        await ctx.progress(current=1, total=2, message="half")
        await ctx.progress(current=2, total=2, message="done")
        return Outcome(result={"n": 2})

    registry["stats"] = work
    op = enqueue(db, "stats", repository_id=repo.id)
    await _drain(runner)
    db.expire_all()
    op = db.get(Operation, op.id)
    assert op.result == {"n": 2}
    assert op.progress_current == 2 and op.progress_total == 2
    assert op.progress_message == "done"
    assert op.log_file_path and op.log_file_path.endswith(f"operation_{op.id}.log")
    assert open(op.log_file_path).read() == "hello\n"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_log_path_resolves_settings_at_call_time(
    db, repo, runner, registry, tmp_path, monkeypatch
):
    """A test elsewhere reloads app.config and leaves a new settings object
    behind (#914). The runner must read app.config.settings when it opens a
    log, not the object it imported at start. Pinned by swapping the object,
    not by reloading the module: a real reload re-runs the module's side
    effects (secret key generation, directory derivation) for every later
    test in the session."""
    import app.config as config

    current_dir = tmp_path / "current"
    monkeypatch.setattr(
        config,
        "settings",
        config.settings.model_copy(update={"data_dir": str(current_dir)}),
    )

    async def work(ctx):
        ctx.log("after swap")
        return Outcome()

    registry["stats"] = work
    op = enqueue(db, "stats", repository_id=repo.id)
    await _drain(runner)
    db.expire_all()
    op = db.get(Operation, op.id)
    expected_path = current_dir / "logs" / f"operation_{op.id}.log"
    assert op.status == "completed"
    assert op.log_file_path == str(expected_path)
    assert expected_path.read_text() == "after swap\n"
    assert not (tmp_path / "logs" / f"operation_{op.id}.log").exists()


@pytest.mark.unit
def test_recover_on_startup(db, repo, runner, monkeypatch):
    idx = enqueue(db, "stats", repository_id=repo.id)
    idx.status = "running"
    idx.started_at = datetime(2026, 9, 1)
    idx.progress_current = 3
    dead = enqueue(db, "check", repository_id=repo.id)
    dead.status = "running"
    dead.process_pid = 4242
    dead.process_start_time = 1.0
    alive = enqueue(db, "compact", repository_id=repo.id)
    alive.status = "running"
    alive.process_pid = 4343
    alive.process_start_time = 2.0
    queued = enqueue(db, "stats", repository_id=repo.id)
    db.commit()
    monkeypatch.setattr(
        "app.services.operations.runner.is_process_alive",
        lambda pid, start: pid == 4343,
    )
    counts = runner.recover_on_startup(db)
    assert counts == {"requeued": 1, "failed": 1, "kept": 1}
    db.expire_all()
    assert db.get(Operation, idx.id).status == "queued"
    assert db.get(Operation, idx.id).started_at is None
    assert db.get(Operation, idx.id).progress_current is None
    assert db.get(Operation, dead.id).status == "failed"
    assert db.get(Operation, dead.id).error_message == "interrupted by restart"
    assert db.get(Operation, alive.id).status == "running"
    assert db.get(Operation, queued.id).status == "queued"


@pytest.mark.unit
def test_recover_on_startup_does_not_break_a_managed_agent_lock(
    db, runner, monkeypatch
):
    """The Borg process for an agent-executed repository runs on the agent
    machine, not the server. Recovery must not call `break_repository_lock`
    against it after a server restart: the agent's own operation, if any, is
    still the one actually holding the lock."""
    agent_repo = Repository(
        name="agent-repo",
        path="/tmp/agent-repo",
        encryption="none",
        compression="lz4",
        executor_type="agent",
        execution_target="agent",
    )
    db.add(agent_repo)
    db.commit()

    dead = enqueue(db, "check", repository_id=agent_repo.id)
    dead.status = "running"
    dead.process_pid = 4242
    dead.process_start_time = 1.0
    db.commit()

    monkeypatch.setattr(
        "app.services.operations.runner.is_process_alive", lambda pid, start: False
    )
    break_lock_calls = []
    monkeypatch.setattr(
        "app.utils.process_utils.break_repository_lock",
        lambda repository: break_lock_calls.append(repository.id) or True,
    )

    runner.recover_on_startup(db)

    assert break_lock_calls == []
    db.expire_all()
    assert db.get(Operation, dead.id).status == "failed"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_start_loop_dispatches_and_stops(db, repo, runner, registry):
    done = asyncio.Event()

    async def ok(ctx):
        done.set()
        return Outcome()

    registry["stats"] = ok
    enqueue(db, "stats", repository_id=repo.id)
    task = asyncio.create_task(runner.start())
    await asyncio.wait_for(done.wait(), timeout=2)
    runner.stop()
    runner.wake()
    await asyncio.wait_for(task, timeout=2)


@pytest.mark.unit
def test_start_survives_a_second_event_loop(session_factory, registry):
    """A production process only ever runs `start()` on one event loop, but
    a test suite that builds a fresh `TestClient(app)` per test starts the
    module-level `operation_runner` on a new loop each time (spec 7.1).
    `asyncio.Event` binds to whichever loop first calls `wait()`/`clear()`
    on it; `_wake` used to be created once and cached, so the second loop's
    `start()` called `wait()` on an Event still bound to the first (closed)
    loop and got `RuntimeError: ... bound to a different event loop`. That
    happens outside `tick()`'s own try/except, so it kills the `start()`
    coroutine outright; nothing awaits that task until shutdown's
    `gather(..., return_exceptions=True)` swallows it, leaving every
    operation from that point queued forever with no visible error.
    `start()` must hand back a fresh event every time it begins."""
    from app.services.operations.runner import OperationRunner

    runner = OperationRunner(session_factory=session_factory, registry=registry)

    async def bind_wake_to_this_loop():
        # Force `_event()` to create an Event and bind it to *this* loop,
        # the way any real tick cycle eventually does inside `start()`.
        try:
            await asyncio.wait_for(runner._event().wait(), timeout=0.01)
        except asyncio.TimeoutError:
            pass

    async def start_and_stop_on_a_fresh_loop():
        task = asyncio.create_task(runner.start())
        await asyncio.sleep(0.05)
        runner.stop()
        runner.wake()
        # Before the fix, `start()` raised inside its own loop the moment it
        # reached `wait()` on the stale, first-loop-bound Event, so this
        # await re-raises that RuntimeError instead of returning cleanly.
        await asyncio.wait_for(task, timeout=2)

    # Two independent event loops, exactly as two integration tests each
    # driving their own `TestClient(app)` do against the same singleton.
    asyncio.run(bind_wake_to_this_loop())
    asyncio.run(start_and_stop_on_a_fresh_loop())


@pytest.mark.unit
def test_start_clears_stale_tasks_from_a_previous_loop(session_factory, registry):
    """`running_tasks` is a plain dict on the module-level singleton, so it
    survives across separate `start()`/`drain()` lifecycles the same way
    `_wake` used to. A task recorded by one lifecycle (e.g. a non-awaitable
    stand-in, from a test that patches `asyncio.create_task` at the moment
    this runner's own tick fires) can never be gathered by a later
    lifecycle's `drain()` anyway, since nothing from that closed loop is
    still running; left in place, `drain()`'s `asyncio.gather(*tasks, ...)`
    blows up on it instead of draining cleanly. `start()` must clear
    `running_tasks` the same way it refreshes `_wake`."""
    from unittest.mock import MagicMock

    from app.services.operations.runner import OperationRunner

    runner = OperationRunner(session_factory=session_factory, registry=registry)
    runner.running_tasks[999] = MagicMock(name="stale_task_from_a_closed_loop")

    async def start_and_stop():
        task = asyncio.create_task(runner.start())
        await asyncio.sleep(0.05)
        runner.stop()
        runner.wake()
        await asyncio.wait_for(task, timeout=2)

    asyncio.run(start_and_stop())

    assert 999 not in runner.running_tasks


@pytest.mark.asyncio
@pytest.mark.parametrize("root_status", ["failed", "cancelled"])
@pytest.mark.parametrize("length", [3, 4])
async def test_dependency_failure_propagates_through_skipped_children(
    db, repo, runner, registry, root_status, length
):
    executed = []

    async def record(ctx):
        executed.append(ctx.kind)
        return Outcome()

    kinds = ["archive_sync", "history_merge", "history_index", "stats"][:length]
    registry.update({kind: record for kind in kinds})
    chain = enqueue_chain(db, kinds, repository_id=repo.id, trigger="reconcile")
    chain[0].status = root_status
    db.commit()
    await _drain(runner)
    db.expire_all()
    assert executed == []
    for op in chain[1:]:
        persisted = db.get(Operation, op.id)
        assert persisted.status == "skipped"
        assert persisted.skip_reason == "dependency_failed"
        assert persisted.completed_at is not None


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize("reason", ["agent_diff_unsupported", "plan_locked"])
async def test_intentional_skip_in_chain_keeps_stats_runnable(
    db, repo, runner, registry, reason
):
    async def ok(ctx):
        return Outcome()

    async def optional_stage(ctx):
        return Outcome(status="skipped", skip_reason=reason)

    registry.update(archive_sync=ok, history_index=optional_stage, stats=ok)
    chain = enqueue_chain(
        db,
        ["archive_sync", "history_index", "stats"],
        repository_id=repo.id,
        trigger="reconcile",
    )
    await _drain(runner)
    db.expire_all()
    rows = [db.get(Operation, op.id) for op in chain]
    assert [op.status for op in rows] == ["completed", "skipped", "completed"]
    assert rows[1].skip_reason == reason
    assert rows[2].skip_reason is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_repository_busy_defers_instead_of_failing(db, repo, runner, registry):
    """Seen live: the follow-up listing is dispatched 45 ms before the plan
    creates its prune job and admission refuses it with 409. The operation
    goes back to the queue with a deferral count and runs on a later tick;
    its dependants are untouched meanwhile."""
    from fastapi import HTTPException

    attempts = []

    async def busy_then_done(ctx):
        attempts.append(ctx.operation_id)
        if len(attempts) == 1:
            raise HTTPException(
                status_code=409,
                detail={"key": "backend.errors.jobs.repositoryOperationActive"},
            )
        return Outcome(result={"listed": 1})

    registry["archive_sync"] = busy_then_done
    registry["stats"] = lambda ctx: _done()
    first = enqueue(db, "archive_sync", repository_id=repo.id)
    child = enqueue(db, "stats", repository_id=repo.id, depends_on_id=first.id)
    await runner.tick()
    await asyncio.gather(*list(runner.running_tasks.values()), return_exceptions=True)
    db.expire_all()
    first = db.get(Operation, first.id)
    assert first.status == "queued" and first.started_at is None
    assert first.params["deferrals"] == 1 and first.error_message is None
    assert db.get(Operation, child.id).status == "queued"
    # a deferral does not wake the runner: no tight retry loop
    assert not runner._event().is_set()

    await _drain(runner)
    db.expire_all()
    assert db.get(Operation, first.id).status == "completed"
    assert db.get(Operation, first.id).result == {"listed": 1}
    assert db.get(Operation, child.id).status == "completed"
    assert len(attempts) == 2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cancel_during_repository_busy_wins_over_the_deferral(
    db, repo, runner, registry
):
    """A cancel that lands while admission is refusing the operation ends it
    as cancelled; requeueing would drop the request in the runner's cleanup
    and the operation would run again on the next tick."""
    from fastapi import HTTPException

    attempts = []

    async def busy(ctx):
        attempts.append(ctx.operation_id)
        runner.cancel_requested.add(ctx.operation_id)
        raise HTTPException(
            status_code=409,
            detail={"key": "backend.errors.jobs.repositoryOperationActive"},
        )

    registry["archive_sync"] = busy
    first = enqueue(db, "archive_sync", repository_id=repo.id)
    await runner.tick()
    await asyncio.gather(*list(runner.running_tasks.values()), return_exceptions=True)
    db.expire_all()
    first = db.get(Operation, first.id)
    assert first.status == "cancelled"
    assert "deferrals" not in (first.params or {})
    assert first.id not in runner.cancel_requested

    await _drain(runner)
    db.expire_all()
    assert db.get(Operation, first.id).status == "cancelled"
    assert len(attempts) == 1


async def _done():
    return Outcome()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_deferral_waits_out_its_delay_despite_wakes(
    db, repo, session_factory, registry, monkeypatch, tmp_path
):
    """Every completion anywhere wakes the runner, and each wake ticks. A
    deferred operation must not be re-dispatched by those ticks until its
    delay has passed, or a busy install burns MAX_DEFERRALS in seconds while
    a pending prune holds the repository."""
    from fastapi import HTTPException

    from app.services.operations import runner as runner_module

    monkeypatch.setattr("app.config.settings.data_dir", str(tmp_path))
    runner = OperationRunner(
        session_factory=session_factory,
        registry=registry,
        poll_interval=0.01,
        deferral_delay=0.2,
    )
    attempts = []

    async def always_busy(ctx):
        attempts.append(ctx.operation_id)
        raise HTTPException(
            status_code=409,
            detail={"key": "backend.errors.jobs.repositoryOperationActive"},
        )

    registry["archive_sync"] = always_busy
    op = enqueue(db, "archive_sync", repository_id=repo.id)
    await _drain(runner, rounds=1)
    db.expire_all()
    row = db.get(Operation, op.id)
    assert row.status == "queued" and row.params["deferrals"] == 1
    not_before = runner_module.deferred_until(row)
    assert not_before is not None and not_before > time.time()

    # ten wakes in a row change nothing
    await _drain(runner, rounds=10)
    db.expire_all()
    assert db.get(Operation, op.id).params["deferrals"] == 1
    assert len(attempts) == 1

    await asyncio.sleep(0.25)
    await _drain(runner, rounds=1)
    db.expire_all()
    row = db.get(Operation, op.id)
    assert row.params["deferrals"] == 2 and len(attempts) == 2
    # the second wait is longer than the first
    assert runner_module.deferred_until(row) - not_before > 0.3

    # the delay doubles and is capped
    assert runner.deferral_delay_for(1) == 0.2
    assert runner.deferral_delay_for(3) == 0.8
    assert (
        runner.deferral_delay_for(runner_module.MAX_DEFERRALS)
        == runner_module.DEFERRAL_MAX_DELAY_SECONDS
    )
    # an unreadable or non-finite not-before never blocks the operation:
    # inf would park it forever, nan would skip the backoff
    for bad in ("not a date", float("inf"), float("nan"), None):
        row.params = {**row.params, "deferred_until": bad}
        assert runner_module.deferred_until(row) is None


@pytest.mark.unit
def test_deferral_count_normalizes_bad_bookkeeping(db, repo):
    """inf overflows int() and a negative count would allow more than
    MAX_DEFERRALS attempts; both read as none, never as a crash that leaves
    the row running."""
    from app.services.operations import runner as runner_module

    op = enqueue(db, "archive_sync", repository_id=repo.id)
    for bad, expected in (
        (float("inf"), 0),
        (float("nan"), 0),
        (-5, 0),
        ("x", 0),
        (None, 0),
        ("3", 3),
        (2.9, 2),
    ):
        op.params = {"deferrals": bad}
        assert runner_module.deferral_count(op) == expected
    op.params = None
    assert runner_module.deferral_count(op) == 0


@pytest.mark.unit
def test_deferred_is_not_an_executor_outcome():
    """Deferral is the runner's reaction to the admission's 409, never an
    executor's choice: an executor cannot requeue itself by returning it."""
    with pytest.raises(ValueError):
        Outcome(status="deferred")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_requeue_commit_failure_fails_the_operation(
    db, repo, runner, registry, monkeypatch
):
    """The requeue commit can fail like any other (locked database). The row
    must not stay `running` with no task behind it until the next restart."""
    from fastapi import HTTPException
    from sqlalchemy.exc import OperationalError
    from sqlalchemy.orm import Session

    real_commit = Session.commit
    fail_next = {"commit": False}

    def flaky_commit(self):
        if fail_next["commit"]:
            fail_next["commit"] = False
            raise OperationalError("UPDATE operations", {}, Exception("locked"))
        return real_commit(self)

    monkeypatch.setattr(Session, "commit", flaky_commit)

    async def busy(ctx):
        fail_next["commit"] = True
        raise HTTPException(
            status_code=409,
            detail={"key": "backend.errors.jobs.repositoryOperationActive"},
        )

    registry["archive_sync"] = busy
    op = enqueue(db, "archive_sync", repository_id=repo.id)
    await _drain(runner, rounds=1)
    db.expire_all()
    op = db.get(Operation, op.id)
    assert op.status == "failed"
    assert "could not requeue" in op.error_message
    assert op.completed_at is not None
    assert (op.params or {}).get("deferrals") is None
    assert not runner.running_tasks


@pytest.mark.unit
@pytest.mark.asyncio
async def test_malformed_persisted_deferrals_do_not_stall_the_operation(
    db, repo, runner, registry
):
    """Unreadable bookkeeping in params counts as no deferrals: the busy
    operation is requeued as a first deferral instead of raising before the
    requeue and leaving the row running."""
    from fastapi import HTTPException

    attempts = []

    async def busy_then_done(ctx):
        attempts.append(ctx.operation_id)
        if len(attempts) == 1:
            raise HTTPException(
                status_code=409,
                detail={"key": "backend.errors.jobs.repositoryOperationActive"},
            )
        return Outcome()

    registry["archive_sync"] = busy_then_done
    op = enqueue(
        db, "archive_sync", repository_id=repo.id, params={"deferrals": "garbage"}
    )
    await _drain(runner, rounds=1)
    db.expire_all()
    row = db.get(Operation, op.id)
    assert row.status == "queued" and row.params["deferrals"] == 1
    await _drain(runner)
    db.expire_all()
    assert db.get(Operation, op.id).status == "completed"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_repository_busy_fails_after_the_deferral_cap(db, repo, runner, registry):
    from fastapi import HTTPException

    from app.services.operations import runner as runner_module

    async def always_busy(ctx):
        raise HTTPException(
            status_code=409,
            detail={"key": "backend.errors.jobs.repositoryOperationActive"},
        )

    registry["archive_sync"] = always_busy
    op = enqueue(db, "archive_sync", repository_id=repo.id)
    await _drain(runner, rounds=runner_module.MAX_DEFERRALS + 5)
    db.expire_all()
    op = db.get(Operation, op.id)
    assert op.status == "failed"
    assert op.params["deferrals"] == runner_module.MAX_DEFERRALS
    assert "still busy" in op.error_message

    # any other exception, and a 409 without the admission key, still fail
    # at once
    async def other(ctx):
        raise HTTPException(status_code=409, detail="something else")

    registry["archive_sync"] = other
    other_op = enqueue(db, "archive_sync", repository_id=repo.id)
    await _drain(runner)
    db.expire_all()
    assert db.get(Operation, other_op.id).status == "failed"
    assert (db.get(Operation, other_op.id).params or {}).get("deferrals") is None
