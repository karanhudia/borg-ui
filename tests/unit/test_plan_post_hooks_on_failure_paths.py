"""Plan post-backup hooks on the ways out of a plan run (#1385).

Once a pre-backup script of a plan run ran, every way out of
`BackupPlanExecutionService.execute_run` runs the post-backup scripts once:
a cancelled run, a pre-backup script failing, and any other error reaching
the run's handler. A cancelled run is a failure to them.
"""

import asyncio
import json
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config import settings
from app.database.models import (
    AgentJob,
    AgentMachine,
    BackupPlanRun,
    BackupPlanScript,
    ScriptExecution,
)
from app.services.backup_plan_execution_service import (
    POST_BACKUP_AGENT_HOOK_TIMEOUT_SECONDS,
    backup_plan_execution_service,
)
from app.services.notification_service import notification_service
from app.services.operations.backup_facade import resolve_backup_job
from tests.utils.operations import seed_job_operation
from tests.unit.test_api_backup_plans import (
    _create_execution_plan,
    _create_repo,
    _create_script,
    _plan_backup_seam,
)


def _hook(test_db, plan, script, hook_type, order, run_on=None):
    test_db.add(
        BackupPlanScript(
            backup_plan_id=plan.id,
            script_id=script.id,
            hook_type=hook_type,
            execution_order=order,
            enabled=True,
            custom_run_on=run_on,
        )
    )


def _scripts(test_db, *names):
    scripts = []
    for name in names:
        script = _create_script(test_db, name)
        path = Path(settings.data_dir) / "scripts" / script.file_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("echo hook\n")
        scripts.append(script)
    return scripts


class _Scripts:
    """A stand-in for `execute_script` that records each script that runs,
    with the backup status it was given, and fails those named in `fail`."""

    def __init__(self, scripts, fail=()):
        self.by_id = {script.id: script.name for script in scripts}
        self.fail = set(fail)
        self.calls = []

    async def __call__(self, script, timeout, env, context):
        script_id = int(context.split(":script:")[1].split(":")[0])
        name = self.by_id[script_id]
        self.calls.append((name, env.get("BORG_UI_BACKUP_STATUS")))
        ok = name not in self.fail
        return {
            "success": ok,
            "exit_code": 0 if ok else 2,
            "stdout": "",
            "stderr": "" if ok else f"{name} broke",
        }


def _completed_backup():
    async def fake_execute_backup(job_id, repository, db, **kwargs):
        job = resolve_backup_job(db, job_id)
        job.status = "completed"
        job.completed_at = datetime.utcnow()
        db.commit()

    return fake_execute_backup


async def _execute(run, scripts, fake_execute_backup=None, *extra):
    patches = [
        patch(
            "app.services.backup_plan_execution_service.execute_script",
            side_effect=scripts.__call__,
        ),
        patch(
            "app.services.operations.backup_facade.wait_for_backup_operation",
            new=_plan_backup_seam(fake_execute_backup or _completed_backup()),
        ),
        patch.object(notification_service, "send_backup_failure", new=AsyncMock()),
        *extra,
    ]
    for item in patches:
        item.start()
    try:
        await backup_plan_execution_service.execute_run(run.id)
    finally:
        for item in reversed(patches):
            item.stop()


def _plan_with_hooks(test_db, *, pre=("Stop Database",)):
    repo = _create_repo(test_db, "Primary", "/repos/primary")
    plan, run = _create_execution_plan(test_db, [repo])
    pre_scripts = _scripts(test_db, *pre)
    on_failure, on_success, always = _scripts(
        test_db, "Start Database", "Report Success", "Always Cleanup"
    )
    for order, script in enumerate(pre_scripts, start=1):
        _hook(test_db, plan, script, "pre-backup", order)
    _hook(test_db, plan, on_failure, "post-backup", 1, run_on="failure")
    _hook(test_db, plan, on_success, "post-backup", 2, run_on="success")
    _hook(test_db, plan, always, "post-backup", 3, run_on="always")
    test_db.commit()
    return run, [*pre_scripts, on_failure, on_success, always]


def _post_calls(scripts):
    return [
        call
        for call in scripts.calls
        if call[0] in ("Start Database", "Report Success", "Always Cleanup")
    ]


@pytest.mark.asyncio
async def test_cancelled_run_runs_post_hooks_as_failure(test_db):
    run, all_scripts = _plan_with_hooks(test_db)
    scripts = _Scripts(all_scripts)

    async def cancelled_backup(job_id, repository, db, **kwargs):
        await backup_plan_execution_service.cancel_run(db, run.id)
        job = resolve_backup_job(db, job_id)
        job.status = "cancelled"
        job.completed_at = datetime.utcnow()
        db.commit()

    await _execute(run, scripts, cancelled_backup)

    assert _post_calls(scripts) == [
        ("Start Database", "failure"),
        ("Always Cleanup", "failure"),
    ]
    test_db.expire_all()
    stored = test_db.get(BackupPlanRun, run.id)
    assert stored.status == "cancelled"
    # the cleanup ran without a warning: only the cancel is left
    assert [json.loads(line)["key"] for line in stored.error_message.split("\n")] == [
        "backend.errors.backup.cancelledByUser"
    ]


@pytest.mark.asyncio
async def test_cancel_after_the_backups_still_counts_as_failure(test_db):
    # every repository completed, then the run was cancelled
    run, all_scripts = _plan_with_hooks(test_db)
    scripts = _Scripts(all_scripts)
    real_series = backup_plan_execution_service._execute_series

    async def series_then_cancel(run_id, context, repositories):
        await real_series(run_id, context, repositories)
        await backup_plan_execution_service.cancel_run(test_db, run_id)

    await _execute(
        run,
        scripts,
        None,
        patch.object(
            backup_plan_execution_service,
            "_execute_series",
            side_effect=series_then_cancel,
        ),
    )

    assert _post_calls(scripts) == [
        ("Start Database", "failure"),
        ("Always Cleanup", "failure"),
    ]


@pytest.mark.asyncio
async def test_later_pre_hook_failing_runs_post_hooks_as_failure(test_db):
    run, all_scripts = _plan_with_hooks(test_db, pre=("Stop Database", "Freeze Volume"))
    scripts = _Scripts(all_scripts, fail={"Freeze Volume"})

    await _execute(run, scripts)

    assert _post_calls(scripts) == [
        ("Start Database", "failure"),
        ("Always Cleanup", "failure"),
    ]
    test_db.expire_all()
    stored = test_db.get(BackupPlanRun, run.id)
    assert stored.status == "failed"
    assert "Freeze Volume" in stored.error_message
    assert [child.status for child in stored.repositories] == ["failed"]


@pytest.mark.asyncio
async def test_single_failing_pre_hook_runs_post_hooks_as_failure(test_db):
    # a pre-backup hook that stopped a service and then exited non-zero
    run, all_scripts = _plan_with_hooks(test_db)
    scripts = _Scripts(all_scripts, fail={"Stop Database"})

    await _execute(run, scripts)

    assert _post_calls(scripts) == [
        ("Start Database", "failure"),
        ("Always Cleanup", "failure"),
    ]


@pytest.mark.asyncio
async def test_error_after_the_pre_hooks_runs_post_hooks_as_failure(test_db):
    run, all_scripts = _plan_with_hooks(test_db)
    scripts = _Scripts(all_scripts)

    await _execute(
        run,
        scripts,
        None,
        patch.object(
            backup_plan_execution_service,
            "_execute_series",
            side_effect=RuntimeError("runner broke"),
        ),
    )

    assert _post_calls(scripts) == [
        ("Start Database", "failure"),
        ("Always Cleanup", "failure"),
    ]
    test_db.expire_all()
    stored = test_db.get(BackupPlanRun, run.id)
    assert stored.status == "failed"
    assert stored.error_message == "runner broke"


@pytest.mark.asyncio
async def test_failing_post_hook_on_the_error_path_is_reported(test_db):
    run, all_scripts = _plan_with_hooks(test_db)
    scripts = _Scripts(all_scripts, fail={"Start Database"})

    await _execute(
        run,
        scripts,
        None,
        patch.object(
            backup_plan_execution_service,
            "_execute_series",
            side_effect=RuntimeError("runner broke"),
        ),
    )

    test_db.expire_all()
    message = test_db.get(BackupPlanRun, run.id).error_message
    assert message.startswith("runner broke; ")
    assert "Start Database" in message


@pytest.mark.asyncio
async def test_error_after_the_post_hooks_does_not_run_them_again(test_db):
    run, all_scripts = _plan_with_hooks(test_db)
    scripts = _Scripts(all_scripts)

    await _execute(
        run,
        scripts,
        None,
        patch.object(
            backup_plan_execution_service,
            "_finalize_run",
            side_effect=RuntimeError("finalize broke"),
        ),
    )

    assert _post_calls(scripts) == [
        ("Report Success", "success"),
        ("Always Cleanup", "success"),
    ]
    test_db.expire_all()
    assert test_db.get(BackupPlanRun, run.id).status == "failed"


@pytest.mark.asyncio
async def test_post_hooks_raising_do_not_run_twice(test_db):
    run, all_scripts = _plan_with_hooks(test_db)
    scripts = _Scripts(all_scripts)
    real_hooks = backup_plan_execution_service._execute_plan_script_hooks
    post_rounds = []

    async def post_hooks_raise(
        run_id, context, *, hook_type, backup_result=None, **kwargs
    ):
        if hook_type == "post-backup":
            post_rounds.append(backup_result)
            raise RuntimeError("hook runner broke")
        return await real_hooks(
            run_id, context, hook_type=hook_type, backup_result=backup_result
        )

    await _execute(
        run,
        scripts,
        None,
        patch.object(
            backup_plan_execution_service,
            "_execute_plan_script_hooks",
            side_effect=post_hooks_raise,
        ),
    )

    assert post_rounds == ["success"]
    test_db.expire_all()
    stored = test_db.get(BackupPlanRun, run.id)
    assert stored.status == "completed_with_warnings"
    assert "hook runner broke" in stored.error_message


@pytest.mark.asyncio
async def test_no_post_hooks_on_an_error_before_any_pre_hook_ran(test_db):
    run, all_scripts = _plan_with_hooks(test_db, pre=())
    scripts = _Scripts(all_scripts)

    await _execute(
        run,
        scripts,
        None,
        patch.object(
            backup_plan_execution_service,
            "_execute_series",
            side_effect=RuntimeError("runner broke"),
        ),
    )

    assert scripts.calls == []
    test_db.expire_all()
    assert (
        test_db.query(ScriptExecution)
        .filter(ScriptExecution.backup_plan_run_id == run.id)
        .count()
        == 0
    )


@pytest.mark.asyncio
async def test_skip_by_a_pre_hook_runs_no_post_hooks(test_db):
    # a graceful skip stands the run down; it is no failure
    repo = _create_repo(test_db, "Primary", "/repos/primary")
    plan, run = _create_execution_plan(test_db, [repo])
    guard, on_failure = _scripts(test_db, "Leader Guard", "Start Database")
    test_db.add(
        BackupPlanScript(
            backup_plan_id=plan.id,
            script_id=guard.id,
            hook_type="pre-backup",
            execution_order=1,
            enabled=True,
            skip_on_failure=True,
        )
    )
    _hook(test_db, plan, on_failure, "post-backup", 1, run_on="failure")
    test_db.commit()
    scripts = _Scripts([guard, on_failure], fail={"Leader Guard"})

    await _execute(run, scripts)

    assert scripts.calls == [("Leader Guard", None)]


@pytest.mark.asyncio
async def test_agent_post_hook_is_not_stopped_by_the_run_cancel(test_db):
    repo = _create_repo(test_db, "Primary", "/repos/primary")
    _plan, run = _create_execution_plan(test_db, [repo])
    run.status = "cancelled"
    test_db.commit()
    context = MagicMock(plan_id=run.backup_plan_id)
    seen = {}
    timeouts = {}

    async def wait(db, agent_job_id, *, is_cancelled, timeout_seconds):
        seen[hook_type_now] = is_cancelled()
        timeouts[hook_type_now] = timeout_seconds
        return {"status": "completed", "result": {"return_code": 0}}

    with (
        patch.object(
            backup_plan_execution_service,
            "_resolve_plan_agent",
            return_value=(MagicMock(), None),
        ),
        patch.object(
            backup_plan_execution_service, "_build_agent_script_env", return_value={}
        ),
        patch(
            "app.services.backup_plan_execution_service.queue_agent_script_job",
            return_value=MagicMock(id=None),
        ),
        patch(
            "app.services.backup_plan_execution_service.dispatch_agent_job_best_effort",
            new=AsyncMock(),
        ),
        patch(
            "app.services.backup_plan_execution_service.wait_for_agent_script_job",
            side_effect=wait,
        ),
    ):
        for hook_type_now in ("pre-backup", "post-backup"):
            await backup_plan_execution_service._execute_agent_plan_script(
                run.id,
                context,
                hook_type=hook_type_now,
                backup_result=None,
                agent_script_name="start-db",
            )

    assert seen == {"pre-backup": True, "post-backup": False}
    # an agent that is away must not hold a run no cancel ends
    assert timeouts == {
        "pre-backup": None,
        "post-backup": POST_BACKUP_AGENT_HOOK_TIMEOUT_SECONDS,
    }


def test_a_cancelled_run_still_running_its_post_hooks_is_active(test_db):
    # a new run's pre-backup hooks must not start under the old run's
    # post-backup hooks
    repo = _create_repo(test_db, "Primary", "/repos/primary")
    plan, run = _create_execution_plan(test_db, [repo])
    run.status = "cancelled"
    test_db.commit()

    assert not backup_plan_execution_service.has_active_run(test_db, plan.id)
    with patch.object(backup_plan_execution_service, "live_run_ids", {run.id}):
        assert backup_plan_execution_service.has_active_run(test_db, plan.id)


@pytest.mark.asyncio
async def test_source_post_scripts_raising_still_run_the_plan_post_hooks(test_db):
    run, all_scripts = _plan_with_hooks(test_db)
    scripts = _Scripts(all_scripts)
    real_source_scripts = backup_plan_execution_service._execute_source_scripts

    async def source_post_raises(run_id, context, *, hook_type, backup_result=None):
        if hook_type == "source-post-backup":
            raise RuntimeError("source scripts broke")
        return await real_source_scripts(
            run_id, context, hook_type=hook_type, backup_result=backup_result
        )

    await _execute(
        run,
        scripts,
        None,
        patch.object(
            backup_plan_execution_service,
            "_execute_source_scripts",
            side_effect=source_post_raises,
        ),
    )

    assert _post_calls(scripts) == [
        ("Report Success", "success"),
        ("Always Cleanup", "success"),
    ]
    test_db.expire_all()
    assert "source scripts broke" in test_db.get(BackupPlanRun, run.id).error_message


@pytest.mark.asyncio
async def test_run_is_failed_when_the_pre_hook_lookup_breaks(test_db):
    run, all_scripts = _plan_with_hooks(test_db)
    scripts = _Scripts(all_scripts)

    await _execute(
        run,
        scripts,
        None,
        patch.object(
            backup_plan_execution_service,
            "_execute_series",
            side_effect=RuntimeError("runner broke"),
        ),
        patch.object(
            backup_plan_execution_service,
            "_pre_backup_scripts_ran",
            side_effect=RuntimeError("database is locked"),
        ),
    )

    test_db.expire_all()
    stored = test_db.get(BackupPlanRun, run.id)
    assert stored.status == "failed"
    assert stored.error_message == "runner broke"


# --- a server restart during the run ---------------------------------------


def _execution(test_db, run, hook_type, status="completed"):
    test_db.add(
        ScriptExecution(
            backup_plan_id=run.backup_plan_id,
            backup_plan_run_id=run.id,
            hook_type=hook_type,
            status=status,
            started_at=datetime.utcnow(),
            triggered_by="backup_plan",
        )
    )
    test_db.commit()


def _interrupted(test_db, run, *executions, child_status="running"):
    run.status = "running"
    for child in run.repositories:
        child.status = child_status
    test_db.commit()
    for hook_type, status in executions:
        _execution(test_db, run, hook_type, status)


def _sweep(test_db):
    from app.utils.process_utils import cleanup_orphaned_jobs

    pending = cleanup_orphaned_jobs(test_db)
    test_db.expire_all()
    return pending


def test_restart_after_the_pre_hooks_leaves_the_post_hooks_pending(test_db):
    run, _scripts_ = _plan_with_hooks(test_db)
    _interrupted(test_db, run, ("pre-backup", "completed"))

    assert _sweep(test_db) == [run.id]

    stored = test_db.get(BackupPlanRun, run.id)
    assert stored.status == "failed"
    keys = [json.loads(line)["key"] for line in stored.error_message.split("\n")]
    assert keys == [
        "backend.errors.service.containerRestartedDuringBackup",
        "backend.errors.service.postBackupHooksAfterRestart",
    ]


def test_restart_after_a_source_pre_script_leaves_the_post_hooks_pending(test_db):
    run, _scripts_ = _plan_with_hooks(test_db, pre=())
    _interrupted(test_db, run, ("source-pre-backup", "failed"))

    assert _sweep(test_db) == [run.id]


def test_restart_before_any_pre_hook_leaves_nothing_pending(test_db):
    run, _scripts_ = _plan_with_hooks(test_db)
    _interrupted(test_db, run)

    assert _sweep(test_db) == []
    stored = test_db.get(BackupPlanRun, run.id)
    assert "postBackupHooksAfterRestart" not in (stored.error_message or "")


def test_restart_after_one_post_hook_ended_does_not_run_them_again(test_db):
    # the source cleanup ended, the plan's own hook had not started: which
    # still had to run is unknown, so the run says so instead
    run, _scripts_ = _plan_with_hooks(test_db)
    _interrupted(
        test_db,
        run,
        ("pre-backup", "completed"),
        ("source-post-backup", "completed"),
    )

    assert _sweep(test_db) == []
    stored = test_db.get(BackupPlanRun, run.id)
    assert "postBackupHooksAfterRestart" in stored.error_message


def test_a_second_restart_before_the_post_hooks_started_finds_them_again(
    test_db,
):
    run, _scripts_ = _plan_with_hooks(test_db)
    _interrupted(test_db, run, ("pre-backup", "completed"))
    assert _sweep(test_db) == [run.id]

    # the process went down again before the recovery ran a post-backup hook
    assert _sweep(test_db) == [run.id]


def test_a_second_restart_after_the_post_hooks_started_does_not_repeat_them(
    test_db,
):
    run, _scripts_ = _plan_with_hooks(test_db)
    _interrupted(test_db, run, ("pre-backup", "completed"))
    assert _sweep(test_db) == [run.id]
    _execution(test_db, run, "post-backup", "running")

    assert _sweep(test_db) == []


def test_a_run_whose_plan_is_gone_is_not_found_again(test_db):
    run, _scripts_ = _plan_with_hooks(test_db)
    _interrupted(test_db, run, ("pre-backup", "completed"))
    assert _sweep(test_db) == [run.id]
    test_db.get(BackupPlanRun, run.id).backup_plan_id = None
    test_db.commit()

    assert _sweep(test_db) == []


def test_restart_during_a_post_hook_does_not_run_it_again(test_db):
    # whether it ended is unknown: the run says so instead
    run, _scripts_ = _plan_with_hooks(test_db)
    _interrupted(test_db, run, ("pre-backup", "completed"), ("post-backup", "running"))

    assert _sweep(test_db) == []
    stored = test_db.get(BackupPlanRun, run.id)
    assert "postBackupHooksAfterRestart" in stored.error_message


def test_restart_after_the_backups_completed_is_a_warning(test_db):
    # every repository completed; the restart came before the post phase
    run, _scripts_ = _plan_with_hooks(test_db)
    _interrupted(test_db, run, ("pre-backup", "completed"), child_status="completed")

    assert _sweep(test_db) == [run.id]
    stored = test_db.get(BackupPlanRun, run.id)
    assert stored.status == "completed_with_warnings"
    assert "postBackupHooksAfterRestart" in stored.error_message


async def _recover(run_ids, *extra):
    patches = [
        patch.object(notification_service, "send_backup_failure", new=AsyncMock()),
        *extra,
    ]
    for item in patches:
        item.start()
    try:
        service = backup_plan_execution_service
        await service._run_post_hooks_after_restart(run_ids[0])
        return patches[0].new
    finally:
        for item in reversed(patches):
            item.stop()


@pytest.mark.asyncio
async def test_post_hooks_run_after_the_restart_as_failure(test_db):
    run, all_scripts = _plan_with_hooks(test_db)
    _interrupted(test_db, run, ("pre-backup", "completed"))
    pending = _sweep(test_db)
    scripts = _Scripts(all_scripts)

    notify = await _recover(
        pending,
        patch(
            "app.services.backup_plan_execution_service.execute_script",
            side_effect=scripts.__call__,
        ),
    )

    assert _post_calls(scripts) == [
        ("Start Database", "failure"),
        ("Always Cleanup", "failure"),
    ]
    test_db.expire_all()
    stored = test_db.get(BackupPlanRun, run.id)
    assert stored.status == "failed"
    assert [json.loads(line)["key"] for line in stored.error_message.split("\n")] == [
        "backend.errors.service.containerRestartedDuringBackup"
    ]
    notify.assert_not_awaited()


@pytest.mark.asyncio
async def test_failing_post_hook_after_the_restart_needs_attention(test_db):
    run, all_scripts = _plan_with_hooks(test_db)
    _interrupted(test_db, run, ("pre-backup", "completed"))
    pending = _sweep(test_db)
    scripts = _Scripts(all_scripts, fail={"Start Database"})

    notify = await _recover(
        pending,
        patch(
            "app.services.backup_plan_execution_service.execute_script",
            side_effect=scripts.__call__,
        ),
    )

    test_db.expire_all()
    lines = test_db.get(BackupPlanRun, run.id).error_message.split("\n")
    assert json.loads(lines[1])["key"] == (
        "backend.errors.service.postBackupHooksAfterRestart"
    )
    assert "Start Database" in lines[2]
    notify.assert_awaited_once()
    assert notify.await_args.args[1] == "/repos/primary"
    # the notification carries readable text, not the stored message keys
    assert "Start Database" in notify.await_args.args[2]
    assert "{" not in notify.await_args.args[2]


@pytest.mark.asyncio
async def test_post_hooks_after_the_restart_wait_for_a_resumed_backup(test_db):
    run, all_scripts = _plan_with_hooks(test_db)
    _interrupted(test_db, run, ("pre-backup", "completed"))
    child = run.repositories[0]
    operation = seed_job_operation(
        test_db, "backup", repository_id=child.repository_id, status="running"
    )
    test_db.commit()
    child.backup_operation_id = operation.id
    test_db.commit()
    pending = _sweep(test_db)
    order = []
    scripts = _Scripts(all_scripts)

    async def wait_out(operation_id, **kwargs):
        order.append(("backup ended", operation_id))
        return "completed"

    async def script(*args, **kwargs):
        order.append(("script", None))
        return await scripts(*args, **kwargs)

    await _recover(
        pending,
        patch(
            "app.services.backup_plan_execution_service.wait_out_backup_operation",
            side_effect=wait_out,
        ),
        patch(
            "app.services.backup_plan_execution_service.execute_script",
            side_effect=script,
        ),
    )

    assert order[0] == ("backup ended", operation.id)
    assert ("script", None) in order[1:]


@pytest.mark.asyncio
async def test_waiting_for_an_agent_job_polls_until_it_ended(test_db):
    statuses = iter(["running", "running", "completed"])
    seen = []

    def load(db):
        status = next(statuses)
        seen.append(status)
        return MagicMock(status=status)

    with patch(
        "app.services.backup_plan_execution_service.AGENT_BACKUP_END_POLL_SECONDS", 0
    ):
        await backup_plan_execution_service._wait_for_agent_job_to_end(load)

    assert seen == ["running", "running", "completed"]


@pytest.mark.asyncio
async def test_post_hooks_after_the_restart_wait_for_agent_jobs_still_running(
    test_db,
):
    # the restart failed the backup and left an agent's pre-backup hook
    # unfinished; either may still run on its agent
    run, all_scripts = _plan_with_hooks(test_db)
    _interrupted(test_db, run, ("pre-backup", "completed"))
    machine = AgentMachine(
        name="Agent",
        agent_id="agt_1385",
        token_hash="unused",
        token_prefix="agt_1385",
        status="online",
    )
    test_db.add(machine)
    test_db.commit()
    agent_job = AgentJob(
        agent_machine_id=machine.id,
        job_type="script.run",
        status="running",
        payload={},
    )
    test_db.add(agent_job)
    test_db.commit()
    test_db.add(
        ScriptExecution(
            backup_plan_id=run.backup_plan_id,
            backup_plan_run_id=run.id,
            hook_type="pre-backup",
            status="running",
            agent_script_name="stop-db",
            agent_job_id=agent_job.id,
            started_at=datetime.utcnow(),
            triggered_by="backup_plan",
        )
    )
    child = run.repositories[0]
    operation = seed_job_operation(
        test_db, "backup", repository_id=child.repository_id, status="running"
    )
    test_db.commit()
    child.backup_operation_id = operation.id
    test_db.commit()
    pending = _sweep(test_db)
    order = []
    scripts = _Scripts(all_scripts)
    real_wait = backup_plan_execution_service._wait_for_agent_job_to_end

    async def wait_out(operation_id, **kwargs):
        order.append(("backup", operation_id))
        return "failed"

    async def wait_for_agent_job(load):
        loaded = load(test_db)
        order.append(("agent job", loaded.id if loaded else None))
        return await real_wait(lambda _db: None)

    async def script(*args, **kwargs):
        order.append(("script", None))
        return await scripts(*args, **kwargs)

    await _recover(
        pending,
        patch(
            "app.services.backup_plan_execution_service.wait_out_backup_operation",
            side_effect=wait_out,
        ),
        patch.object(
            backup_plan_execution_service,
            "_wait_for_agent_job_to_end",
            side_effect=wait_for_agent_job,
        ),
        patch(
            "app.services.backup_plan_execution_service.execute_script",
            side_effect=script,
        ),
    )

    assert order[:3] == [
        ("backup", operation.id),
        ("agent job", None),
        ("agent job", agent_job.id),
    ]
    assert order[3] == ("script", None)


@pytest.mark.asyncio
async def test_a_deleted_plan_after_the_restart_needs_attention(test_db):
    run, _scripts_ = _plan_with_hooks(test_db)
    _interrupted(test_db, run, ("pre-backup", "completed"))
    pending = _sweep(test_db)

    with patch.object(backup_plan_execution_service, "_query_plan", return_value=None):
        notify = await _recover(pending)

    test_db.expire_all()
    message = test_db.get(BackupPlanRun, run.id).error_message
    assert "postBackupHooksAfterRestart" in message
    assert "Backup plan no longer exists" in message
    notify.assert_awaited_once()


@pytest.mark.asyncio
async def test_a_run_is_live_while_its_post_hooks_run_after_the_restart(test_db):
    run, _scripts_ = _plan_with_hooks(test_db)
    finish = asyncio.Event()

    async def post_hooks(run_id):
        await finish.wait()

    service = backup_plan_execution_service
    with (
        patch.object(service, "_run_post_hooks_after_restart", side_effect=post_hooks),
        patch.object(service, "live_run_ids", set()),
    ):
        service.recover_post_hooks_after_restart([run.id])
        await asyncio.sleep(0)
        assert service.live_run_ids == {run.id}
        assert service.has_active_run(test_db, run.backup_plan_id)
        finish.set()
        for _ in range(20):
            if not service.live_run_ids:
                break
            await asyncio.sleep(0.01)
        assert service.live_run_ids == set()


def test_startup_runs_the_pending_post_hooks():
    import app.main as main

    with (
        patch("app.utils.process_utils.cleanup_orphaned_jobs", return_value=[7, 8]),
        patch.object(
            backup_plan_execution_service, "recover_post_hooks_after_restart"
        ) as recover,
        patch(
            "app.api.repositories.resume_pending_initial_cloud_mirror_sync_operations",
            return_value=0,
        ),
    ):
        main._recover_interrupted_work()

    recover.assert_called_once_with([7, 8])


@pytest.mark.asyncio
async def test_failing_cleanup_of_a_cancelled_run_is_reported(test_db):
    run, all_scripts = _plan_with_hooks(test_db)
    scripts = _Scripts(all_scripts, fail={"Start Database"})

    async def cancelled_backup(job_id, repository, db, **kwargs):
        await backup_plan_execution_service.cancel_run(db, run.id)
        job = resolve_backup_job(db, job_id)
        job.status = "cancelled"
        job.completed_at = datetime.utcnow()
        db.commit()

    notify = AsyncMock()
    await _execute(
        run,
        scripts,
        cancelled_backup,
        patch.object(notification_service, "send_backup_failure", new=notify),
    )

    test_db.expire_all()
    stored = test_db.get(BackupPlanRun, run.id)
    assert stored.status == "cancelled"
    lines = stored.error_message.split("\n")
    assert json.loads(lines[0])["key"] == "backend.errors.backup.cancelledByUser"
    assert json.loads(lines[1])["key"] == (
        "backend.errors.service.postBackupHooksAfterCancel"
    )
    assert "Start Database" in lines[2]
    notify.assert_awaited_once()
    assert notify.await_args.args[1] == "/repos/primary"
    # the notification carries readable text, not the stored message keys
    assert "Start Database" in notify.await_args.args[2]
    assert "{" not in notify.await_args.args[2]


@pytest.mark.asyncio
async def test_cancel_after_a_pre_hook_says_the_cleanup_is_still_to_run(test_db):
    run, _scripts_ = _plan_with_hooks(test_db)
    run.status = "running"
    test_db.commit()
    _execution(test_db, run, "pre-backup")

    with patch(
        "app.services.operations.runner.operation_runner.request_cancel",
        new=AsyncMock(return_value=False),
    ):
        await backup_plan_execution_service.cancel_run(test_db, run.id)

    test_db.expire_all()
    keys = [
        json.loads(line)["key"]
        for line in test_db.get(BackupPlanRun, run.id).error_message.split("\n")
    ]
    assert keys == [
        "backend.errors.backup.cancelledByUser",
        "backend.errors.service.postBackupHooksAfterCancel",
    ]


@pytest.mark.asyncio
async def test_cancel_before_any_pre_hook_says_nothing_more(test_db):
    run, _scripts_ = _plan_with_hooks(test_db)
    run.status = "running"
    test_db.commit()

    await backup_plan_execution_service.cancel_run(test_db, run.id)

    test_db.expire_all()
    assert test_db.get(BackupPlanRun, run.id).error_message == (
        '{"key": "backend.errors.backup.cancelledByUser"}'
    )


@pytest.mark.asyncio
async def test_restart_between_the_cancel_and_its_cleanup_runs_the_cleanup(
    test_db,
):
    run, all_scripts = _plan_with_hooks(test_db)
    run.status = "running"
    test_db.commit()
    _execution(test_db, run, "pre-backup")
    await backup_plan_execution_service.cancel_run(test_db, run.id)
    test_db.expire_all()

    # the process went down before the cancelled run's own task ran them
    pending = _sweep(test_db)
    assert pending == [run.id]
    scripts = _Scripts(all_scripts)
    notify = await _recover(
        pending,
        patch(
            "app.services.backup_plan_execution_service.execute_script",
            side_effect=scripts.__call__,
        ),
    )

    assert _post_calls(scripts) == [
        ("Start Database", "failure"),
        ("Always Cleanup", "failure"),
    ]
    test_db.expire_all()
    stored = test_db.get(BackupPlanRun, run.id)
    assert stored.status == "cancelled"
    assert [json.loads(line)["key"] for line in stored.error_message.split("\n")] == [
        "backend.errors.backup.cancelledByUser"
    ]
    notify.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_queued_agent_job_of_the_interrupted_run_is_ended_not_waited_for(
    test_db,
):
    # an agent that is away would leave it queued for a day; it must not
    # start later either
    machine = AgentMachine(
        name="Agent",
        agent_id="agt_1385_queued",
        token_hash="unused",
        token_prefix="agt_1385",
        status="offline",
    )
    test_db.add(machine)
    test_db.commit()
    agent_job = AgentJob(
        agent_machine_id=machine.id,
        job_type="script.run",
        status="queued",
        payload={},
    )
    test_db.add(agent_job)
    test_db.commit()

    with patch(
        "app.services.backup_plan_execution_service.AGENT_BACKUP_END_POLL_SECONDS", 0
    ):
        await asyncio.wait_for(
            backup_plan_execution_service._wait_for_agent_job_to_end(
                lambda db: db.get(AgentJob, agent_job.id)
            ),
            timeout=5,
        )

    test_db.expire_all()
    ended = test_db.get(AgentJob, agent_job.id)
    assert ended.status == "canceled"
    assert ended.completed_at is not None
