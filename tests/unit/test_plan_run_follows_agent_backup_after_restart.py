"""A plan run whose backup an agent kept running through a server restart.

The startup sweep leaves such a run active instead of failing it, and the run
is followed from there: the backup is seen through as in the run itself, the
plan's post-backup scripts hear the result the run came to, and the run is
finished from what its repositories ended as. Repositories the run had not
started stay interrupted.
"""

import asyncio
import json
from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest

from app.database.models import (
    AgentJob,
    AgentMachine,
    BackupPlanRun,
    Operation,
    ScriptExecution,
)
from app.services.backup_plan_execution_service import backup_plan_execution_service
from app.services.notification_service import notification_service
from app.utils.process_utils import cleanup_orphaned_jobs
from tests.unit.test_api_backup_plans import _create_execution_plan, _create_repo
from tests.unit.test_plan_post_hooks_on_failure_paths import (
    _interrupted,
    _plan_with_hooks,
    _post_calls,
    _Scripts,
)
from tests.utils.operations import seed_job_operation

RESTARTED = "backend.errors.service.containerRestartedDuringBackup"


def _agent_backup(test_db, child, *, agent_job_status="running"):
    """The repository's backup as the restart found it: the operation
    `running`, carried by an agent job."""
    machine = test_db.query(AgentMachine).first()
    if machine is None:
        machine = AgentMachine(
            name="Agent",
            agent_id="agt_1177",
            token_hash="unused",
            token_prefix="agt_1177",
            status="online",
        )
        test_db.add(machine)
        test_db.commit()
    operation = seed_job_operation(
        test_db, "backup", repository_id=child.repository_id, status="running"
    )
    test_db.commit()
    child.backup_operation_id = operation.id
    test_db.add(
        AgentJob(
            agent_machine_id=machine.id,
            job_type="backup",
            status=agent_job_status,
            payload={},
            operation_id=operation.id,
        )
    )
    test_db.commit()
    return operation


def _sweep(test_db):
    following: list[int] = []
    pending = cleanup_orphaned_jobs(test_db, agent_backups_running=following)
    test_db.expire_all()
    return pending, following


def _keys(message):
    return [json.loads(line)["key"] for line in (message or "").split("\n") if line]


def _backup_ends(test_db, status, error_message=None):
    """A stand-in for the wait on the backup operation: the agent's report
    ended it meanwhile."""
    waited = []

    async def wait_out(operation_id, **kwargs):
        waited.append(operation_id)
        operation = test_db.get(Operation, operation_id)
        if operation.status == "running":
            operation.status = status
            operation.error_message = error_message
            operation.completed_at = datetime.utcnow()
            for agent_job in test_db.query(AgentJob).filter(
                AgentJob.operation_id == operation_id
            ):
                agent_job.status = "canceled" if status == "cancelled" else status
            test_db.commit()
        return operation.status

    return waited, wait_out


async def _follow(run, wait_out, scripts=None, *extra):
    patches = [
        patch(
            "app.services.backup_plan_execution_service.wait_out_backup_operation",
            side_effect=wait_out,
        ),
        patch.object(notification_service, "send_backup_failure", new=AsyncMock()),
        *extra,
    ]
    if scripts is not None:
        patches.append(
            patch(
                "app.services.backup_plan_execution_service.execute_script",
                side_effect=scripts.__call__,
            )
        )
    for item in patches:
        item.start()
    try:
        await backup_plan_execution_service._follow_agent_backups_after_restart(run.id)
    finally:
        for item in reversed(patches):
            item.stop()


def test_the_sweep_leaves_a_run_open_whose_agent_still_runs_its_backup(test_db):
    run, _all = _plan_with_hooks(test_db)
    _interrupted(test_db, run, ("pre-backup", "completed"))
    operation = _agent_backup(test_db, run.repositories[0])

    pending, following = _sweep(test_db)

    # its post-backup scripts wait for the backup, with the run
    assert (pending, following) == ([], [run.id])
    stored = test_db.get(BackupPlanRun, run.id)
    assert stored.status == "running"
    assert stored.error_message is None
    assert [child.status for child in stored.repositories] == ["running"]
    assert test_db.get(Operation, operation.id).status == "running"


@pytest.mark.parametrize("agent_job_status", ["completed", "failed", "canceled"])
def test_a_run_whose_agent_job_ended_is_finished_as_before(test_db, agent_job_status):
    run, _all = _plan_with_hooks(test_db)
    _interrupted(test_db, run, ("pre-backup", "completed"))
    _agent_backup(test_db, run.repositories[0], agent_job_status=agent_job_status)

    pending, following = _sweep(test_db)

    assert (pending, following) == ([run.id], [])
    assert test_db.get(BackupPlanRun, run.id).status == "failed"


def test_a_caller_that_follows_no_run_gets_every_run_finished(test_db):
    run, _all = _plan_with_hooks(test_db)
    _interrupted(test_db, run)
    _agent_backup(test_db, run.repositories[0])

    cleanup_orphaned_jobs(test_db)
    test_db.expire_all()

    assert test_db.get(BackupPlanRun, run.id).status == "failed"


def test_repositories_the_run_had_not_started_stay_interrupted(test_db):
    first = _create_repo(test_db, "First", "/repos/first")
    second = _create_repo(test_db, "Second", "/repos/second")
    _plan, run = _create_execution_plan(test_db, [first, second])
    run.status = "running"
    running, waiting = run.repositories
    running.status = "running"
    waiting.status = "pending"
    test_db.commit()
    _agent_backup(test_db, running)
    queued = seed_job_operation(
        test_db, "backup", repository_id=second.id, status="pending"
    )
    queued.backup_plan_run_id = run.id
    queued.trigger = "plan"
    test_db.commit()

    _pending, following = _sweep(test_db)

    assert following == [run.id]
    stored = test_db.get(BackupPlanRun, run.id)
    assert stored.status == "running"
    by_repository = {child.repository_id: child for child in stored.repositories}
    assert by_repository[first.id].status == "running"
    assert by_repository[second.id].status == "failed"
    assert _keys(by_repository[second.id].error_message) == [RESTARTED]
    assert test_db.get(Operation, queued.id).status == "cancelled"


@pytest.mark.asyncio
async def test_a_followed_run_ends_as_its_backup_did(test_db):
    run, all_scripts = _plan_with_hooks(test_db)
    _interrupted(test_db, run, ("pre-backup", "completed"))
    operation = _agent_backup(test_db, run.repositories[0])
    _sweep(test_db)
    scripts = _Scripts(all_scripts)
    waited, wait_out = _backup_ends(test_db, "completed")
    maintenance = AsyncMock(return_value=None)

    await _follow(
        run,
        wait_out,
        scripts,
        patch.object(backup_plan_execution_service, "_run_maintenance", maintenance),
    )

    assert set(waited) == {operation.id}
    maintenance.assert_awaited_once()
    # the scripts hear the backup's own result, not a failure for the restart
    assert _post_calls(scripts) == [
        ("Report Success", "success"),
        ("Always Cleanup", "success"),
    ]
    test_db.expire_all()
    stored = test_db.get(BackupPlanRun, run.id)
    assert stored.status == "completed"
    assert stored.error_message is None
    assert stored.completed_at is not None
    assert [child.status for child in stored.repositories] == ["completed"]


@pytest.mark.asyncio
async def test_a_followed_backup_that_failed_fails_its_run(test_db):
    run, all_scripts = _plan_with_hooks(test_db)
    _interrupted(test_db, run, ("pre-backup", "completed"))
    _agent_backup(test_db, run.repositories[0])
    _sweep(test_db)
    scripts = _Scripts(all_scripts)
    _waited, wait_out = _backup_ends(test_db, "failed", "borg exited with code 2")
    maintenance = AsyncMock(return_value=None)

    await _follow(
        run,
        wait_out,
        scripts,
        patch.object(backup_plan_execution_service, "_run_maintenance", maintenance),
    )

    maintenance.assert_not_awaited()
    assert _post_calls(scripts) == [
        ("Start Database", "failure"),
        ("Always Cleanup", "failure"),
    ]
    test_db.expire_all()
    stored = test_db.get(BackupPlanRun, run.id)
    assert stored.status == "failed"
    child = stored.repositories[0]
    assert (child.status, child.error_message) == ("failed", "borg exited with code 2")
    # the backup's own failure, not the restart's
    assert stored.error_message is None


@pytest.mark.asyncio
async def test_a_followed_run_says_what_the_restart_cost_it(test_db):
    first = _create_repo(test_db, "First", "/repos/first")
    second = _create_repo(test_db, "Second", "/repos/second")
    _plan, run = _create_execution_plan(test_db, [first, second])
    run.status = "running"
    running, waiting = run.repositories
    running.status = "running"
    waiting.status = "pending"
    test_db.commit()
    _agent_backup(test_db, running)
    _sweep(test_db)
    _waited, wait_out = _backup_ends(test_db, "completed")

    await _follow(run, wait_out)

    test_db.expire_all()
    stored = test_db.get(BackupPlanRun, run.id)
    assert stored.status == "partial"
    assert _keys(stored.error_message) == [RESTARTED]
    assert sorted(child.status for child in stored.repositories) == [
        "completed",
        "failed",
    ]


@pytest.mark.asyncio
async def test_a_run_is_live_while_it_is_followed(test_db):
    run, _all = _plan_with_hooks(test_db)
    _interrupted(test_db, run)
    _agent_backup(test_db, run.repositories[0])
    _pending, following = _sweep(test_db)
    service = backup_plan_execution_service
    started = asyncio.Event()
    finish = asyncio.Event()

    async def follow(run_id):
        started.set()
        await finish.wait()

    with patch.object(
        service, "_follow_agent_backups_after_restart", side_effect=follow
    ):
        service.follow_agent_backups_after_restart(following)
        await started.wait()
        assert run.id in service.live_run_ids
        finish.set()
        for _ in range(20):
            if run.id not in service.live_run_ids:
                break
            await asyncio.sleep(0.01)
    assert run.id not in service.live_run_ids


def test_startup_follows_the_runs_the_sweep_left_open():
    import app.main as main

    def sweep(db, live_run_ids, *, hold_for_post_hooks, agent_backups_running):
        agent_backups_running.extend([5, 6])
        return [7]

    with (
        patch("app.utils.process_utils.cleanup_orphaned_jobs", side_effect=sweep),
        patch.object(backup_plan_execution_service, "recover_post_hooks_after_restart"),
        patch.object(
            backup_plan_execution_service, "follow_agent_backups_after_restart"
        ) as follow,
        patch(
            "app.api.repositories.resume_pending_initial_cloud_mirror_sync_operations",
            return_value=0,
        ),
    ):
        main._recover_interrupted_work()

    follow.assert_called_once_with([5, 6])


@pytest.mark.asyncio
async def test_a_plan_with_only_post_backup_scripts_runs_them_after_its_backup(
    test_db,
):
    """A backup of the run had its slot, so the run itself would run its
    post-backup scripts; no pre-backup script has to have left a record."""
    run, all_scripts = _plan_with_hooks(test_db, pre=())
    _interrupted(test_db, run)
    _agent_backup(test_db, run.repositories[0])
    pending, following = _sweep(test_db)
    assert (pending, following) == ([], [run.id])
    scripts = _Scripts(all_scripts)
    _waited, wait_out = _backup_ends(test_db, "completed")

    await _follow(run, wait_out, scripts)

    assert _post_calls(scripts) == [
        ("Report Success", "success"),
        ("Always Cleanup", "success"),
    ]
    test_db.expire_all()
    assert test_db.get(BackupPlanRun, run.id).status == "completed"


@pytest.mark.asyncio
async def test_a_failing_cleanup_after_a_failed_backup_is_recorded_and_notified(
    test_db,
):
    run, all_scripts = _plan_with_hooks(test_db)
    _interrupted(test_db, run, ("pre-backup", "completed"))
    _agent_backup(test_db, run.repositories[0])
    _sweep(test_db)
    scripts = _Scripts(all_scripts, fail=("Start Database",))
    _waited, wait_out = _backup_ends(test_db, "failed", "borg exited with code 2")

    notify = AsyncMock()
    await _follow(
        run,
        wait_out,
        scripts,
        patch.object(notification_service, "send_backup_failure", new=notify),
    )

    test_db.expire_all()
    stored = test_db.get(BackupPlanRun, run.id)
    assert stored.status == "failed"
    # what the pre-backup script stopped may still be stopped
    assert _keys(stored.error_message.split("\n")[0]) == [
        "backend.errors.service.postBackupHooksAfterRestart"
    ]
    assert "Start Database" in stored.error_message
    notify.assert_awaited()


@pytest.mark.asyncio
async def test_a_backup_whose_repository_a_cancel_closed_is_still_waited_for(
    test_db,
):
    """A cancel of the run between the sweep and its follower closes the
    repository at once, while the agent may still be stopping the backup:
    the plan's post-backup scripts wait for that backup all the same."""
    run, all_scripts = _plan_with_hooks(test_db)
    _interrupted(test_db, run, ("pre-backup", "completed"))
    operation = _agent_backup(test_db, run.repositories[0])
    _sweep(test_db)
    stored = test_db.get(BackupPlanRun, run.id)
    stored.status = "cancelled"
    stored.repositories[0].status = "cancelled"
    test_db.commit()
    order = []
    scripts = _Scripts(all_scripts)
    _waited, backup_ends = _backup_ends(test_db, "cancelled")

    async def wait_out(operation_id, **kwargs):
        order.append("backup ended")
        return await backup_ends(operation_id, **kwargs)

    async def script(*args, **kwargs):
        order.append("script")
        return await scripts(*args, **kwargs)

    await _follow(
        run,
        wait_out,
        None,
        patch(
            "app.services.backup_plan_execution_service.execute_script",
            side_effect=script,
        ),
    )

    assert order[0] == "backup ended"
    assert "script" in order[1:]
    assert _post_calls(scripts) == [
        ("Start Database", "failure"),
        ("Always Cleanup", "failure"),
    ]
    test_db.expire_all()
    stored = test_db.get(BackupPlanRun, run.id)
    assert stored.status == "cancelled"
    assert [child.status for child in stored.repositories] == ["cancelled"]
    assert test_db.get(Operation, operation.id).status == "cancelled"


@pytest.mark.asyncio
async def test_following_a_backup_holds_no_connection_while_it_runs(test_db):
    """As in the run itself, where the wait starts after a commit: the
    follower's session has ended its read before the wait."""
    import app.services.backup_plan_execution_service as service_module

    run, _all = _plan_with_hooks(test_db)
    _interrupted(test_db, run)
    _agent_backup(test_db, run.repositories[0])
    _sweep(test_db)
    opened = []
    real_session = service_module.SessionLocal

    def tracked():
        session = real_session()
        opened.append(session)
        return session

    _waited, backup_ends = _backup_ends(test_db, "completed")
    open_reads = []

    async def wait_out(operation_id, **kwargs):
        test_db.rollback()
        open_reads.append(
            [s for s in opened if s is not test_db and s.in_transaction()]
        )
        return await backup_ends(operation_id, **kwargs)

    await _follow(
        run,
        wait_out,
        None,
        patch.object(service_module, "SessionLocal", side_effect=tracked),
    )

    assert open_reads and open_reads[0] == []


@pytest.mark.asyncio
@pytest.mark.parametrize("pre_status", ["warning", "failed"])
async def test_what_a_pre_backup_script_left_to_say_before_the_restart_is_kept(
    test_db, pre_status
):
    """The verdict of the pre-backup scripts went with the process; a
    warning one of them ended with, or a failure the run was allowed to go
    on after, is on its execution."""
    run, all_scripts = _plan_with_hooks(test_db)
    _interrupted(test_db, run)
    test_db.add(
        ScriptExecution(
            backup_plan_id=run.backup_plan_id,
            backup_plan_run_id=run.id,
            hook_type="pre-backup",
            status=pre_status,
            error_message="exit code 1 (warning)",
            started_at=datetime.utcnow(),
            triggered_by="backup_plan",
        )
    )
    test_db.commit()
    _agent_backup(test_db, run.repositories[0])
    _sweep(test_db)
    scripts = _Scripts(all_scripts)
    _waited, wait_out = _backup_ends(test_db, "completed")

    await _follow(run, wait_out, scripts)

    test_db.expire_all()
    stored = test_db.get(BackupPlanRun, run.id)
    assert stored.status == "completed_with_warnings"
    assert stored.error_message == "exit code 1 (warning)"


def _report_before_the_sweep(test_db, operation, *, result=None):
    """The agent's report ended the backup in a process that had not
    recovered yet; `result` is what only the runner's own task writes."""
    operation.status = "completed"
    operation.completed_at = datetime.utcnow()
    operation.result = result
    for agent_job in test_db.query(AgentJob).filter(
        AgentJob.operation_id == operation.id
    ):
        agent_job.status = "completed"
    test_db.commit()


@pytest.mark.asyncio
async def test_a_backup_the_agents_report_ended_before_the_sweep_is_followed(
    test_db,
):
    """The row carries the agent's verdict, but no task saw the backup
    through: the run still owes it its maintenance and its status."""
    run, all_scripts = _plan_with_hooks(test_db)
    _interrupted(test_db, run, ("pre-backup", "completed"))
    operation = _agent_backup(test_db, run.repositories[0])
    _report_before_the_sweep(test_db, operation)

    pending, following = _sweep(test_db)
    assert (pending, following) == ([], [run.id])
    scripts = _Scripts(all_scripts)
    _waited, wait_out = _backup_ends(test_db, "completed")
    maintenance = AsyncMock(return_value=None)

    await _follow(
        run,
        wait_out,
        scripts,
        patch.object(backup_plan_execution_service, "_run_maintenance", maintenance),
    )

    maintenance.assert_awaited_once()
    assert _post_calls(scripts) == [
        ("Report Success", "success"),
        ("Always Cleanup", "success"),
    ]
    test_db.expire_all()
    stored = test_db.get(BackupPlanRun, run.id)
    assert stored.status == "completed"
    assert [child.status for child in stored.repositories] == ["completed"]


def test_a_backup_that_ended_before_the_restart_is_not_followed(test_db):
    """With the runner's result on the row the backup was over before the
    restart: what the restart interrupted was the run's maintenance, and
    the run is finished as before."""
    run, _all = _plan_with_hooks(test_db)
    _interrupted(test_db, run)
    operation = _agent_backup(test_db, run.repositories[0])
    _report_before_the_sweep(test_db, operation, result={"archive": "a"})

    _pending, following = _sweep(test_db)

    assert following == []
    stored = test_db.get(BackupPlanRun, run.id)
    assert stored.status == "failed"
    assert _keys(stored.repositories[0].error_message) == [RESTARTED]


@pytest.mark.asyncio
async def test_a_follower_that_fails_leaves_the_cleanup_to_the_restart_recovery(
    test_db,
):
    """The run fails, and still says that its post-backup scripts are to
    run: the recovery of those scripts takes it from there, now and after
    any later restart."""
    run, _all = _plan_with_hooks(test_db)
    _interrupted(test_db, run, ("pre-backup", "completed"))
    _agent_backup(test_db, run.repositories[0])
    _sweep(test_db)
    service = backup_plan_execution_service
    seen = []

    async def recover(run_id):
        test_db.expire_all()
        seen.append(test_db.get(BackupPlanRun, run_id).error_message.split("\n"))

    with (
        patch.object(
            service, "_pre_backup_warnings", side_effect=RuntimeError("no database")
        ),
        patch.object(service, "_run_post_hooks_after_restart", side_effect=recover),
    ):
        await service._follow_agent_backups_after_restart(run.id)

    test_db.expire_all()
    stored = test_db.get(BackupPlanRun, run.id)
    assert stored.status == "failed"
    assert "no database" in stored.error_message
    assert len(seen) == 1
    assert _keys(seen[0][-1]) == ["backend.errors.service.postBackupHooksAfterRestart"]
