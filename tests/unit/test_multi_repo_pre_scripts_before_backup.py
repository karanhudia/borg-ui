"""A multi-repository schedule that runs the repositories' own scripts
starts a repository's backup only after that repository's pre-backup
scripts ran (#1431).

The schedule creates the backup operation before the scripts (they get its
id) as held, and no runner starts it until the schedule releases it. One a
restart left held is cancelled at startup.
"""

import asyncio
from unittest.mock import patch

import pytest
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

from app.api import schedule as schedule_api
from app.database.models import (
    Operation,
    ScheduledJob,
    ScheduledJobRepository,
    SystemSettings,
)
from app.services.operations import backup_facade
from app.services.operations.backup_facade import (
    create_backup_operation,
    release_backup_operation,
)
from app.services.operations.runner import (
    HOLD_PARAM,
    PROCESS_HOLD_ID,
    OperationRunner,
    Outcome,
)

from tests.unit.test_backup_post_hooks_after_restart import _repository


def _schedule(test_db, repository, *, run_repository_scripts=True):
    if test_db.query(SystemSettings).first() is None:
        test_db.add(SystemSettings())
    schedule = ScheduledJob(
        name="nightly",
        cron_expression="0 2 * * *",
        enabled=True,
        run_repository_scripts=run_repository_scripts,
    )
    test_db.add(schedule)
    test_db.commit()
    test_db.add(
        ScheduledJobRepository(
            scheduled_job_id=schedule.id,
            repository_id=repository.id,
            execution_order=0,
        )
    )
    test_db.commit()
    return schedule


@pytest.fixture
def runner(test_db):
    """A runner on the test database whose backup executor only records
    that it started."""
    started = []

    async def backup(ctx):
        started.append(ctx.operation_id)
        return Outcome()

    runner = OperationRunner(
        session_factory=sessionmaker(bind=test_db.get_bind()),
        registry={"backup": backup},
        poll_interval=0.01,
    )
    runner.started = started
    return runner


async def _tick(runner):
    await runner.tick()
    await asyncio.gather(*runner.running_tasks.values(), return_exceptions=True)


def _wait_with(runner):
    """Stand in for the wait on the backup: the runner looks once more."""

    async def wait(db, operation_id, **kwargs):
        await _tick(runner)
        db.expire_all()
        return db.get(Operation, operation_id).status

    return patch(
        "app.services.operations.backup_facade.wait_for_backup_operation", new=wait
    )


async def _run(test_db, schedule):
    await asyncio.wait_for(
        schedule_api.execute_multi_repo_schedule(schedule, test_db), 30
    )
    test_db.expire_all()
    return test_db.query(Operation).filter(Operation.kind == "backup").one()


@pytest.mark.asyncio
async def test_the_runner_leaves_the_backup_queued_while_its_pre_scripts_run(
    test_db, runner
):
    schedule = _schedule(test_db, _repository(test_db))
    during = []

    async def script(**kwargs):
        if kwargs["hook_type"] == "pre-backup":
            # the runner looks while the script runs
            await _tick(runner)
            during.append(list(runner.started))
        return {"success": True}

    with (
        patch.object(schedule_api, "run_script_from_library", side_effect=script),
        _wait_with(runner),
    ):
        backup = await _run(test_db, schedule)

    assert during == [[]]
    assert runner.started == [backup.id]
    assert backup.status == "completed"
    assert HOLD_PARAM not in backup.params


@pytest.mark.asyncio
async def test_a_failed_pre_script_releases_the_backup(test_db, runner):
    # the schedule goes on with the backup when a pre-backup script fails
    schedule = _schedule(test_db, _repository(test_db))

    async def script(**kwargs):
        if kwargs["hook_type"] == "pre-backup":
            await _tick(runner)
            raise RuntimeError("Script stop-db failed: exit 1")
        return {"success": True}

    with (
        patch.object(schedule_api, "run_script_from_library", side_effect=script),
        _wait_with(runner),
    ):
        backup = await _run(test_db, schedule)

    assert runner.started == [backup.id]
    assert backup.status == "completed"
    assert HOLD_PARAM not in backup.params


@pytest.mark.asyncio
async def test_a_schedule_cancelled_in_its_pre_scripts_cancels_its_backup(
    test_db, runner
):
    # a shutdown, say: the schedule would not run the post-backup scripts
    schedule = _schedule(test_db, _repository(test_db))

    async def pre_script(**kwargs):
        raise asyncio.CancelledError()

    with patch.object(schedule_api, "run_script_from_library", side_effect=pre_script):
        with pytest.raises(asyncio.CancelledError):
            await schedule_api.execute_multi_repo_schedule(schedule, test_db)

    await _tick(runner)
    assert runner.started == []
    test_db.expire_all()
    backup = test_db.query(Operation).filter(Operation.kind == "backup").one()
    assert backup.status == "cancelled"
    assert backup.completed_at is not None


@pytest.mark.asyncio
async def test_a_backup_without_the_schedules_scripts_is_not_held(test_db, runner):
    # the backup runs the repository's scripts itself
    schedule = _schedule(test_db, _repository(test_db), run_repository_scripts=False)
    script_calls = []
    held = []

    def create(*args, **kwargs):
        held.append(kwargs.get("held"))
        return create_backup_operation(*args, **kwargs)

    with (
        patch.object(
            schedule_api,
            "run_script_from_library",
            side_effect=lambda **kwargs: script_calls.append(kwargs),
        ),
        patch.object(schedule_api, "create_backup_operation", side_effect=create),
        _wait_with(runner),
    ):
        backup = await _run(test_db, schedule)

    assert script_calls == []
    assert held == [False]
    assert runner.started == [backup.id]


@pytest.mark.asyncio
async def test_no_runner_starts_a_held_backup_until_it_is_released(test_db, runner):
    repository = _repository(test_db)
    test_db.add(SystemSettings())
    test_db.commit()
    job = create_backup_operation(
        test_db, repository, trigger="schedule", executor="server", held=True
    )
    assert test_db.get(Operation, job.id).params[HOLD_PARAM] == PROCESS_HOLD_ID

    # this runner is not the process's: the hold is on the row
    await _tick(runner)
    assert runner.started == []
    test_db.expire_all()
    assert test_db.get(Operation, job.id).status == "queued"

    await release_backup_operation(job.id)
    await _tick(runner)
    assert runner.started == [job.id]


@pytest.mark.asyncio
async def test_a_release_waits_out_a_database_error(test_db, runner, monkeypatch):
    repository = _repository(test_db)
    job = create_backup_operation(
        test_db, repository, trigger="schedule", executor="server", held=True
    )
    factory = sessionmaker(bind=test_db.get_bind())
    sessions = []

    def locked(*args, **kwargs):
        raise OperationalError("SELECT", {}, Exception("database is locked"))

    def session():
        # the first read fails
        db = factory()
        if not sessions:
            db.get = locked
        sessions.append(db)
        return db

    monkeypatch.setattr("app.database.database.SessionLocal", session)
    monkeypatch.setattr(backup_facade, "BACKUP_WAIT_BACKOFF_SECONDS", 0)

    await release_backup_operation(job.id)

    assert len(sessions) == 2
    test_db.expire_all()
    assert HOLD_PARAM not in test_db.get(Operation, job.id).params


def test_startup_cancels_a_backup_a_gone_process_held(test_db, runner):
    repository = _repository(test_db)
    gone = create_backup_operation(
        test_db, repository, trigger="schedule", executor="server", held=True
    )
    gone.operation.params = {**gone.operation.params, HOLD_PARAM: "gone"}
    own = create_backup_operation(
        test_db, repository, trigger="schedule", executor="server", held=True
    )
    free = create_backup_operation(
        test_db, repository, trigger="schedule", executor="server"
    )
    test_db.commit()

    runner.recover_on_startup(test_db)

    test_db.expire_all()
    cancelled = test_db.get(Operation, gone.id)
    assert cancelled.status == "cancelled"
    assert cancelled.error_message == "interrupted by restart"
    assert cancelled.completed_at is not None
    # a schedule started while the runner waited for the lease
    assert test_db.get(Operation, own.id).status == "queued"
    assert test_db.get(Operation, free.id).status == "queued"


@pytest.mark.asyncio
async def test_the_schedule_holds_no_connection_while_it_releases(test_db, runner):
    # a release waiting for a free connection must not hold one itself
    schedule = _schedule(test_db, _repository(test_db))
    seen = []

    async def release(operation_id):
        seen.append(test_db.in_transaction())
        await release_backup_operation(operation_id)

    async def script(**kwargs):
        return {"success": True}

    with (
        patch.object(schedule_api, "run_script_from_library", side_effect=script),
        patch.object(schedule_api, "release_backup_operation", side_effect=release),
        _wait_with(runner),
    ):
        backup = await _run(test_db, schedule)

    assert seen == [False]
    assert runner.started == [backup.id]


@pytest.mark.asyncio
async def test_a_schedule_cancelled_in_the_release_cancels_its_backup(test_db, runner):
    schedule = _schedule(test_db, _repository(test_db))

    async def script(**kwargs):
        return {"success": True}

    async def release(operation_id):
        # the wait for a free database ends with the schedule
        raise asyncio.CancelledError()

    with (
        patch.object(schedule_api, "run_script_from_library", side_effect=script),
        patch.object(schedule_api, "release_backup_operation", side_effect=release),
    ):
        with pytest.raises(asyncio.CancelledError):
            await schedule_api.execute_multi_repo_schedule(schedule, test_db)

    test_db.expire_all()
    backup = test_db.query(Operation).filter(Operation.kind == "backup").one()
    assert backup.status == "cancelled"
    await _tick(runner)
    assert runner.started == []


@pytest.mark.asyncio
async def test_a_schedule_that_fails_before_the_release_cancels_its_backup(
    test_db, runner
):
    # a database that closed the schedule's transaction, say: the schedule
    # leaves the repository without its post-backup scripts
    schedule = _schedule(test_db, _repository(test_db))

    async def script(**kwargs):
        return {"success": True}

    with (
        patch.object(schedule_api, "run_script_from_library", side_effect=script),
        patch.object(
            schedule_api,
            "release_backup_operation",
            side_effect=RuntimeError("connection closed"),
        ),
    ):
        await asyncio.wait_for(
            schedule_api.execute_multi_repo_schedule(schedule, test_db), 30
        )

    test_db.expire_all()
    backup = test_db.query(Operation).filter(Operation.kind == "backup").one()
    assert backup.status == "cancelled"
    await _tick(runner)
    assert runner.started == []


def test_a_failed_hold_sweep_keeps_the_rest_of_the_recovery(test_db, runner):
    repository = _repository(test_db)
    interrupted = create_backup_operation(
        test_db, repository, trigger="schedule", executor="server"
    )
    interrupted.operation.status = "running"
    test_db.commit()

    gone = create_backup_operation(
        test_db, repository, trigger="schedule", executor="server", held=True
    )
    gone.operation.params = {**gone.operation.params, HOLD_PARAM: "gone"}
    test_db.commit()

    with patch.object(
        runner, "_cancel_abandoned_holds", side_effect=RuntimeError("locked")
    ):
        runner.recover_on_startup(test_db)

    test_db.expire_all()
    assert test_db.get(Operation, interrupted.id).status == "failed"
    assert test_db.get(Operation, gone.id).status == "queued"


@pytest.mark.asyncio
async def test_the_tick_retries_a_failed_hold_sweep(test_db, runner):
    repository = _repository(test_db)
    gone = create_backup_operation(
        test_db, repository, trigger="schedule", executor="server", held=True
    )
    gone.operation.params = {**gone.operation.params, HOLD_PARAM: "gone"}
    test_db.commit()
    with patch.object(
        runner, "_cancel_abandoned_holds", side_effect=RuntimeError("locked")
    ):
        runner.recover_on_startup(test_db)

    await _tick(runner)

    test_db.expire_all()
    assert test_db.get(Operation, gone.id).status == "cancelled"
    assert runner.started == []


@pytest.mark.asyncio
async def test_a_recovery_that_fails_before_its_sweep_leaves_it_to_the_tick(
    test_db, runner
):
    repository = _repository(test_db)
    test_db.add(SystemSettings())
    gone = create_backup_operation(
        test_db, repository, trigger="schedule", executor="server", held=True
    )
    gone.operation.params = {**gone.operation.params, HOLD_PARAM: "gone"}
    test_db.commit()

    with patch.object(runner, "recover_on_startup", side_effect=RuntimeError("locked")):
        loop = asyncio.create_task(runner.start())
        for _ in range(50):
            await asyncio.sleep(0.01)
            test_db.expire_all()
            if test_db.get(Operation, gone.id).status != "queued":
                break
        runner.stop()
        runner.wake()
        await asyncio.wait_for(loop, 5)

    assert test_db.get(Operation, gone.id).status == "cancelled"
    assert runner.started == []


@pytest.mark.asyncio
async def test_a_cancel_the_schedule_could_not_write_is_left_to_the_tick(
    test_db, runner, monkeypatch
):
    monkeypatch.setattr("app.services.operations.runner.operation_runner", runner)
    repository = _repository(test_db)
    job = create_backup_operation(
        test_db, repository, trigger="schedule", executor="server", held=True
    )

    with patch.object(test_db, "commit", side_effect=RuntimeError("locked")):
        schedule_api._cancel_queued_backup(test_db, job.id)

    test_db.expire_all()
    assert test_db.get(Operation, job.id).status == "queued"
    await _tick(runner)
    test_db.expire_all()
    assert test_db.get(Operation, job.id).status == "cancelled"
    assert runner.started == []
    assert not runner.holds_to_cancel


@pytest.mark.asyncio
async def test_a_retried_hold_sweep_leaves_a_successors_hold(test_db, runner):
    # a replacement process holds a backup while this runner still has the
    # lease and retries its sweep
    repository = _repository(test_db)
    with patch.object(
        runner, "_cancel_abandoned_holds", side_effect=RuntimeError("locked")
    ):
        runner.recover_on_startup(test_db)
    successor = create_backup_operation(
        test_db, repository, trigger="schedule", executor="server", held=True
    )
    successor.operation.params = {**successor.operation.params, HOLD_PARAM: "next"}
    test_db.commit()

    await _tick(runner)

    test_db.expire_all()
    assert test_db.get(Operation, successor.id).status == "queued"
    assert runner.started == []
