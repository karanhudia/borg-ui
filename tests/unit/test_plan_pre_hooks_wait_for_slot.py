"""A plan run's pre-backup scripts run when its first backup gets its slot in
the queue, right before `borg create`, not when the run starts. A run that
waits behind another machine's backup must not keep what its scripts stop
(Docker containers, a database) down for that whole wait, and a run cancelled
while queued runs neither its pre- nor its post-backup scripts.
"""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest

from app.database.models import BackupPlanRun, Operation, ScriptExecution
from app.services.backup_plan_execution_service import backup_plan_execution_service
from app.services.notification_service import notification_service
from app.services.operations.backup_facade import resolve_backup_job
from app.services.operations.executors import get_executor, load_default_executors
from tests.unit.test_api_backup_plans import (
    _create_execution_plan,
    _create_repo,
    _plan_backup_seam,
)
from tests.unit.test_operations_backup_executor import FakeContext
from tests.unit.test_plan_post_hooks_on_failure_paths import _hook, _scripts, _Scripts


def _plan(test_db):
    repo = _create_repo(test_db, "Primary", "/repos/primary")
    plan, run = _create_execution_plan(test_db, [repo])
    stop, start = _scripts(test_db, "Stop Containers", "Start Containers")
    _hook(test_db, plan, stop, "pre-backup", 1)
    _hook(test_db, plan, start, "post-backup", 1, run_on="always")
    test_db.commit()
    return run, _Scripts([stop, start])


async def _settle():
    for _ in range(50):
        await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_a_queued_plan_runs_its_pre_script_only_once_its_slot_opens(test_db):
    load_default_executors()
    run, scripts = _plan(test_db)
    slot_open = asyncio.Event()
    queued = asyncio.Event()
    events = []

    async def runner(db, operation_id, **_ignored):
        # The plan's backup waits in the queue behind another backup.
        assert db.get(Operation, operation_id).status == "queued"
        queued.set()
        await slot_open.wait()
        operation = db.get(Operation, operation_id)
        operation.status = "running"
        operation.started_at = datetime.utcnow()
        db.commit()
        outcome = await get_executor("backup")(FakeContext(db, operation))
        db.expire_all()
        operation = db.get(Operation, operation_id)
        operation.status = outcome.status
        db.commit()
        return operation.status

    async def borg_create(job_id, repository_path, session, **kwargs):
        events.append(("borg create", [name for name, _ in scripts.calls]))
        job = resolve_backup_job(test_db, job_id)
        job.status = "completed"
        job.completed_at = datetime.utcnow()
        test_db.commit()

    with (
        patch(
            "app.services.backup_plan_execution_service.execute_script",
            side_effect=scripts.__call__,
        ),
        patch(
            "app.services.operations.backup_facade.wait_for_backup_operation",
            new=runner,
        ),
        patch(
            "app.services.backup_service.backup_service.execute_backup",
            new=borg_create,
        ),
        patch.object(notification_service, "send_backup_failure", new=AsyncMock()),
    ):
        task = asyncio.create_task(backup_plan_execution_service.execute_run(run.id))
        await asyncio.wait_for(queued.wait(), 5)
        await _settle()

        assert scripts.calls == []  # nothing stopped while the backup waits

        slot_open.set()
        await asyncio.wait_for(task, 5)

    assert events == [("borg create", ["Stop Containers"])]
    assert scripts.calls == [
        ("Stop Containers", None),
        ("Start Containers", "success"),
    ]
    test_db.expire_all()
    assert test_db.get(BackupPlanRun, run.id).status == "completed"


@pytest.mark.asyncio
async def test_a_plan_cancelled_while_queued_runs_no_script(test_db):
    run, scripts = _plan(test_db)

    async def cancelled_in_the_queue(db, operation_id, **_ignored):
        assert db.get(Operation, operation_id).status == "queued"
        await backup_plan_execution_service.cancel_run(db, run.id)
        db.expire_all()
        return db.get(Operation, operation_id).status

    with (
        patch(
            "app.services.backup_plan_execution_service.execute_script",
            side_effect=scripts.__call__,
        ),
        patch(
            "app.services.operations.backup_facade.wait_for_backup_operation",
            new=cancelled_in_the_queue,
        ),
    ):
        await backup_plan_execution_service.execute_run(run.id)

    assert scripts.calls == []
    test_db.expire_all()
    stored = test_db.get(BackupPlanRun, run.id)
    assert stored.status == "cancelled"
    # no cleanup is announced for scripts that never ran
    assert stored.error_message == '{"key": "backend.errors.backup.cancelledByUser"}'
    assert [op.status for op in test_db.query(Operation)] == ["cancelled"]
    assert (
        test_db.query(ScriptExecution)
        .filter(ScriptExecution.backup_plan_run_id == run.id)
        .count()
        == 0
    )


@pytest.mark.asyncio
async def test_a_backup_of_an_ended_run_stands_down(test_db):
    # A restart failed the run; its backup must not start without the
    # scripts the run would have run.
    _repo = _create_repo(test_db, "Primary", "/repos/primary")
    _plan, run = _create_execution_plan(test_db, [_repo])
    run.status = "failed"
    test_db.commit()

    verdict = await backup_plan_execution_service.enter_backup_slot(run.id)

    assert verdict.status == "skipped"


@pytest.mark.asyncio
async def test_a_pre_script_that_raises_leaves_no_repository_pending(test_db):
    repo_a = _create_repo(test_db, "Primary", "/repos/primary")
    repo_b = _create_repo(test_db, "Secondary", "/repos/secondary")
    _plan, run = _create_execution_plan(test_db, [repo_a, repo_b])

    async def broken_hooks(run_id, context, *, hook_type, **kwargs):
        raise RuntimeError("script lookup broke")

    async def no_backup(*args, **kwargs):
        raise AssertionError("the broken pre-backup script stops the run first")

    with (
        patch.object(
            backup_plan_execution_service,
            "_execute_plan_script_hooks",
            side_effect=broken_hooks,
        ),
        patch(
            "app.services.operations.backup_facade.wait_for_backup_operation",
            new=_plan_backup_seam(no_backup),
        ),
        patch.object(notification_service, "send_backup_failure", new=AsyncMock()),
    ):
        await backup_plan_execution_service.execute_run(run.id)

    test_db.expire_all()
    stored = test_db.get(BackupPlanRun, run.id)
    assert stored.status == "failed"
    assert "script lookup broke" in stored.error_message
    assert [child.status for child in stored.repositories] == ["failed", "failed"]
