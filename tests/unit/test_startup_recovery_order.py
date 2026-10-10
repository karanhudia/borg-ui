"""Startup order of the scheduler against the lease-gated startup sweeps
(#1398): the sweep fails every active backup plan run, so nothing may create
one before it has run."""

import asyncio
import json
from contextlib import ExitStack
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.models import (
    Base,
    BackupPlan,
    BackupPlanRepository,
    BackupPlanRun,
    BackupPlanRunRepository,
    Repository,
    SystemSettings,
)
from app.services.operations.runner import OperationRunner


@pytest.fixture()
def session_factory():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


@pytest.fixture()
def due_plan(session_factory):
    db = session_factory()
    try:
        db.add(SystemSettings())
        repo = Repository(
            name="r",
            path="/tmp/r",
            encryption="none",
            compression="lz4",
            repository_type="local",
        )
        db.add(repo)
        db.flush()
        # next_run passed while the process was down: the scheduler's first
        # tick dispatches it as a catch-up run
        plan = BackupPlan(
            name="p",
            source_directories=json.dumps(["/src"]),
            enabled=True,
            schedule_enabled=True,
            cron_expression="45 * * * *",
            next_run=datetime.utcnow() - timedelta(minutes=3),
        )
        db.add(plan)
        db.flush()
        db.add(
            BackupPlanRepository(
                backup_plan_id=plan.id,
                repository_id=repo.id,
                enabled=True,
                execution_order=1,
                created_at=datetime.utcnow(),
            )
        )
        db.commit()
        return plan.id
    finally:
        db.close()


@pytest.fixture()
def lease_db(session_factory):
    """A session of the process being replaced, which holds the lease."""
    db = session_factory()
    try:
        yield db
    finally:
        db.close()


def _plan_runs(session_factory, plan_id):
    db = session_factory()
    try:
        return [
            (run.trigger, run.status)
            for run in db.query(BackupPlanRun)
            .filter(BackupPlanRun.backup_plan_id == plan_id)
            .order_by(BackupPlanRun.id)
        ]
    finally:
        db.close()


async def _wait_for(predicate, timeout=3.0):
    for _ in range(int(timeout / 0.01)):
        if predicate():
            return True
        await asyncio.sleep(0.01)
    return predicate()


def _startup_patches(stack, session_factory, runner):
    """Run the real startup order with the real scheduler loop, plan
    dispatch, startup sweeps and runner; everything else is stubbed. Plan
    runs stay where the sweep can see them, active and being prepared, until
    the returned event is set."""
    finish_runs = asyncio.Event()

    async def preparing(run_id):
        await finish_runs.wait()

    for target, kwargs in [
        ("app.main.create_first_user", {"new_callable": AsyncMock}),
        ("app.database.db_upgrade.ensure_schema", {}),
        ("app.main.settings.enable_startup_license_sync", {"new": False}),
        ("app.database.database.SessionLocal", {"new": session_factory}),
        ("app.api.schedule.SessionLocal", {"new": session_factory}),
        ("app.services.cache_service.archive_cache", {}),
        ("app.core.borg.borg.get_system_info", {"new_callable": AsyncMock}),
        ("app.services.backup_service.backup_service", {}),
        ("app.utils.process_utils.cleanup_orphaned_mounts", {}),
        (
            "app.api.repositories.resume_pending_initial_cloud_mirror_sync_operations",
            {"return_value": 0},
        ),
        ("app.api.schedule.dispatch_due_scheduled_backups", {"new": AsyncMock()}),
        ("app.api.schedule.run_due_scheduled_checks", {"new": AsyncMock()}),
        ("app.api.schedule.run_due_scheduled_restore_checks", {"new": AsyncMock()}),
        ("app.api.schedule.dispatch_due_scheduled_rclone_mirrors", {}),
        ("app.api.schedule.run_backup_monitoring_and_reports", {"new": AsyncMock()}),
        (
            "app.services.backup_plan_execution_service."
            "backup_plan_execution_service.execute_run",
            {"new": preparing},
        ),
        # not the ids earlier tests left in the process-wide service
        (
            "app.services.backup_plan_execution_service."
            "backup_plan_execution_service.live_run_ids",
            {"new": set(), "create": True},
        ),
        ("app.services.operations.runner.operation_runner", {"new": runner}),
        (
            "app.services.operations.reconcile.reconcile_scheduler",
            {"new": Mock(start=AsyncMock())},
        ),
        ("app.services.operations.reconcile.bootstrap_history_once", {}),
        ("app.services.mqtt_service.mqtt_service", {}),
        (
            "app.services.mqtt_sync_scheduler.start_mqtt_sync_scheduler",
            {"new": AsyncMock()},
        ),
        ("app.services.agent_job_reaper.start_agent_job_reaper", {"new": AsyncMock()}),
        (
            "app.services.job_history_retention.start_job_history_retention",
            {"new": AsyncMock()},
        ),
    ]:
        stack.enter_context(patch(target, **kwargs))
    return finish_runs


async def _stop(app, runner, finish_runs):
    runner.stop()
    runner.wake()
    for task in app.state.background_tasks:
        task.cancel()
    await asyncio.gather(*app.state.background_tasks, return_exceptions=True)
    finish_runs.set()
    await asyncio.sleep(0.01)


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize("lease_handed_over", [True, False])
async def test_catch_up_plan_run_survives_the_startup_sweep(
    session_factory, due_plan, lease_handed_over, lease_db
):
    """A plan run the scheduler dispatches at startup is this process's own
    work: the sweep must not fail it as interrupted by the restart. With the
    lease free, the scheduler task is created first and dispatches before
    the runner's first iteration; when the process being replaced did not
    hand the lease over, the window is the wait for it to expire."""
    old = OperationRunner(session_factory=session_factory, registry={})
    if not lease_handed_over:
        assert old.acquire_lease(lease_db)
    runner = OperationRunner(
        session_factory=session_factory, registry={}, poll_interval=0.01
    )

    with ExitStack() as stack:
        finish_runs = _startup_patches(stack, session_factory, runner)
        from app.main import app, startup_event

        app.state.background_tasks = []
        await startup_event()
        try:
            await asyncio.sleep(0.1)
            if not lease_handed_over:
                assert _plan_runs(session_factory, due_plan) == []
            old.release_lease(lease_db)  # it expires or is handed over
            assert await _wait_for(lambda: runner._holds_lease)
            assert await _wait_for(lambda: _plan_runs(session_factory, due_plan)), (
                "the scheduler dispatched nothing"
            )
            await asyncio.sleep(0.1)
        finally:
            await _stop(app, runner, finish_runs)

    assert _plan_runs(session_factory, due_plan) == [("schedule", "pending")]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_manual_plan_run_in_the_lease_wait_survives_the_startup_sweep(
    session_factory, due_plan, lease_db
):
    """The API serves requests while the runner still waits for the lease;
    a plan run started by hand in that window is this process's own work
    too."""
    db = session_factory()
    plan = db.get(BackupPlan, due_plan)
    plan.schedule_enabled = False
    db.commit()
    db.close()
    old = OperationRunner(session_factory=session_factory, registry={})
    assert old.acquire_lease(lease_db)
    runner = OperationRunner(
        session_factory=session_factory, registry={}, poll_interval=0.01
    )

    with ExitStack() as stack:
        finish_runs = _startup_patches(stack, session_factory, runner)
        from app.main import app, startup_event
        from app.services.backup_plan_execution_service import (
            backup_plan_execution_service,
        )

        app.state.background_tasks = []
        await startup_event()
        try:
            await asyncio.sleep(0.05)
            db = session_factory()
            try:
                run_id = backup_plan_execution_service.start_run(
                    db, db.get(BackupPlan, due_plan), trigger="manual"
                )
            finally:
                db.close()
            assert backup_plan_execution_service.live_run_ids == {run_id}
            old.release_lease(lease_db)
            assert await _wait_for(lambda: runner._holds_lease)
            await asyncio.sleep(0.1)
        finally:
            await _stop(app, runner, finish_runs)

    assert _plan_runs(session_factory, due_plan) == [("manual", "pending")]


@pytest.mark.unit
def test_startup_sweep_fails_only_plan_runs_this_process_is_not_executing(
    session_factory, due_plan
):
    from app.utils.process_utils import cleanup_orphaned_jobs

    db = session_factory()
    try:
        runs = [
            BackupPlanRun(
                backup_plan_id=due_plan,
                trigger="schedule",
                status=status,
                created_at=datetime.utcnow(),
            )
            for status in ("running", "pending", "pending")
        ]
        db.add_all(runs)
        db.commit()
        left_behind, live = runs[0].id, runs[1].id

        cleanup_orphaned_jobs(db, {live})

        statuses = {run.id: run.status for run in db.query(BackupPlanRun)}
        assert statuses == {
            left_behind: "failed",
            live: "pending",
            runs[2].id: "failed",
        }
    finally:
        db.close()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_the_scheduler_runs_when_the_runner_ends_before_its_recovery(
    session_factory, due_plan
):
    """No sweep runs after a runner that died before its recovery, so the
    scheduler has nothing to wait for."""

    def broken_database():
        raise RuntimeError("database unavailable")

    runner = OperationRunner(
        session_factory=broken_database, registry={}, poll_interval=0.01
    )

    with ExitStack() as stack:
        finish_runs = _startup_patches(stack, session_factory, runner)
        from app.main import app, startup_event

        app.state.background_tasks = []
        await startup_event()
        try:
            assert await _wait_for(lambda: _plan_runs(session_factory, due_plan)), (
                "the scheduler dispatched nothing"
            )
        finally:
            await _stop(app, runner, finish_runs)

    assert _plan_runs(session_factory, due_plan) == [("schedule", "pending")]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_a_shutdown_during_the_lease_wait_does_not_start_the_scheduler(
    session_factory, due_plan, lease_db
):
    """A runner stopped before its recovery is shutting down: the scheduler
    must not dispatch work no sweep has seen and nothing will run."""
    old = OperationRunner(session_factory=session_factory, registry={})
    assert old.acquire_lease(lease_db)
    runner = OperationRunner(
        session_factory=session_factory, registry={}, poll_interval=0.01
    )

    with ExitStack() as stack:
        finish_runs = _startup_patches(stack, session_factory, runner)
        from app.main import app, startup_event

        app.state.background_tasks = []
        await startup_event()
        try:
            await asyncio.sleep(0.05)
            runner.stop()
            runner.wake()
            assert await _wait_for(lambda: runner._loop_exited)
            await asyncio.sleep(0.1)
        finally:
            await _stop(app, runner, finish_runs)
            old.release_lease(lease_db)

    assert _plan_runs(session_factory, due_plan) == []


def _failed_run(db, plan_id):
    plan = db.get(BackupPlan, plan_id)
    run = BackupPlanRun(
        backup_plan_id=plan_id,
        trigger="schedule",
        status="failed",
        created_at=datetime.utcnow(),
    )
    db.add(run)
    db.flush()
    db.add(
        BackupPlanRunRepository(
            backup_plan_run_id=run.id,
            repository_id=plan.repositories[0].repository_id,
            status="failed",
        )
    )
    db.commit()
    return run


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["start", "retry"])
async def test_a_plan_run_is_live_while_its_execution_task_runs(
    session_factory, due_plan, path
):
    from app.services.backup_plan_execution_service import BackupPlanExecutionService

    service = BackupPlanExecutionService()
    finish = asyncio.Event()

    async def preparing(run_id):
        await finish.wait()

    service.execute_run = preparing
    db = session_factory()
    try:
        if path == "start":
            run_id = service.start_run(
                db, db.get(BackupPlan, due_plan), trigger="manual"
            )
        else:
            run_id = service.retry_failed_run(
                db, _failed_run(db, due_plan), requested_by_user_id=None
            )
    finally:
        db.close()
    assert service.live_run_ids == {run_id}

    finish.set()
    assert await _wait_for(lambda: not service.live_run_ids)
