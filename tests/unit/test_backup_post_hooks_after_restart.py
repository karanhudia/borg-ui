"""Post-backup hooks of a server backup a restart interrupted (#1429).

A backup the restart interrupted after its repository's pre-backup hooks
ran runs its post-backup hooks after the restart, once, with the failure
result. The backup says so until they ran without a failure; when they fail
or cannot run, the line stays and a notification goes out. As for plan runs
(#1385), the marker is the script executions the hooks leave.
"""

import asyncio
import json
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.config import settings
from app.database.models import (
    BackupPlanRun,
    Operation,
    Repository,
    RepositoryScript,
    Script,
    ScriptExecution,
)
from app.services.backup_service import backup_service
from app.services.notification_service import notification_service
from app.services.operations.runner import operation_runner
from app.utils.process_utils import (
    BACKUP_POST_HOOKS_AFTER_RESTART,
    backup_post_hooks_after_restart,
)
from tests.utils.operations import seed_job_operation

MARKER_KEY = "backend.errors.service.backupPostHooksAfterRestart"


def _repository(test_db, *, post=(("start-db", "failure"), ("cleanup", "always"))):
    """A server repository with a library pre-backup script and the
    post-backup scripts `post` as (name, run_on)."""
    repository = Repository(
        name="db-host", path="/backups/db-host", encryption="none", compression="lz4"
    )
    test_db.add(repository)
    test_db.commit()
    specs = [("stop-db", "pre-backup", None), *((n, "post-backup", r) for n, r in post)]
    for order, (name, hook_type, run_on) in enumerate(specs, start=1):
        script = Script(name=name, file_path=f"{name}.sh", category="custom")
        test_db.add(script)
        test_db.commit()
        path = Path(settings.data_dir) / "scripts" / script.file_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("echo hook\n")
        test_db.add(
            RepositoryScript(
                repository_id=repository.id,
                script_id=script.id,
                hook_type=hook_type,
                execution_order=order,
                enabled=True,
                custom_run_on=run_on,
                continue_on_error=False,
            )
        )
    test_db.commit()
    return repository


def _backup(test_db, repository, *executions, status="running", error=None, ended=None):
    """A backup operation with the script executions its hooks left, as
    (hook_type, agent script name or None). One not running reached its end,
    and the runner wrote its result, unless `ended` is False."""
    operation = seed_job_operation(
        test_db, "backup", repository_id=repository.id, status=status
    )
    operation.started_at = datetime.utcnow()
    # the service writes `completed_at` with the outcome, before its
    # archive statistics and post-backup hooks
    if status != "running":
        operation.completed_at = datetime.utcnow()
    if ended if ended is not None else status != "running":
        operation.result = {"archive_name": "archive"}
    test_db.commit()
    if error is not None:
        operation.error_message = error
    for hook_type, agent_script_name in executions:
        test_db.add(
            ScriptExecution(
                repository_id=repository.id,
                operation_id=operation.id,
                agent_script_name=agent_script_name,
                hook_type=hook_type,
                status="completed",
                started_at=datetime.utcnow(),
                triggered_by="backup",
            )
        )
    test_db.commit()
    return operation


class _Scripts:
    """A stand-in for `execute_script` that records each script that runs,
    with the backup status it was given, and fails those named in `fail`."""

    def __init__(self, test_db, fail=()):
        self.names = {script.id: script.name for script in test_db.query(Script)}
        self.fail = set(fail)
        self.calls = []

    async def __call__(self, script, timeout, env, context):
        script_id = int(context.split(":script:")[1])
        name = self.names[script_id]
        self.calls.append((name, env.get("BORG_UI_BACKUP_STATUS")))
        ok = name not in self.fail
        return {
            "success": ok,
            "exit_code": 0 if ok else 2,
            "stdout": "",
            "stderr": "" if ok else f"{name} broke",
        }


def _boot(test_db):
    """What a start does: the sweep, then the runner's own recovery."""
    found = backup_post_hooks_after_restart(test_db)
    with patch.object(operation_runner, "_recover_repository_lock"):
        operation_runner.recover_on_startup(test_db)
    test_db.expire_all()
    return found


async def _recover(test_db, found, scripts):
    notify = AsyncMock()
    with (
        patch("app.services.script_library_executor.execute_script", new=scripts),
        patch.object(notification_service, "send_backup_failure", new=notify),
    ):
        for operation_id, _repository_id, state in found:
            await backup_service._post_hooks_after_restart(operation_id, state)
    test_db.expire_all()
    return notify


def _lines(test_db, operation_id):
    return test_db.get(Operation, operation_id).error_message.split("\n")


def _keys(lines):
    keys = []
    for line in lines:
        try:
            keys.append(json.loads(line)["key"])
        except ValueError:
            keys.append(line)
    return keys


# --- what the sweep finds ----------------------------------------------------


def test_restart_after_the_pre_hooks_leaves_the_post_hooks_pending(test_db):
    repository = _repository(test_db)
    backup = _backup(test_db, repository, ("pre-backup", None))

    assert _boot(test_db) == [(backup.id, repository.id, "pending")]
    assert test_db.get(Operation, backup.id).status == "failed"


def test_restart_before_any_pre_hook_leaves_nothing_pending(test_db):
    repository = _repository(test_db)
    _backup(test_db, repository)

    assert _boot(test_db) == []


def test_restart_after_a_post_hook_started_does_not_run_them_again(test_db):
    repository = _repository(test_db)
    backup = _backup(test_db, repository, ("pre-backup", None), ("post-backup", None))

    assert _boot(test_db) == [(backup.id, repository.id, "interrupted")]


def test_agent_hooks_are_not_looked_at(test_db):
    # an agent repository's hooks run on its agent
    repository = _repository(test_db)
    _backup(test_db, repository, ("pre-backup", "stop-db"))

    assert _boot(test_db) == []


def test_plan_scripts_are_not_a_repository_hook(test_db):
    repository = _repository(test_db)
    backup = _backup(test_db, repository)
    run = BackupPlanRun(status="running", trigger="manual")
    test_db.add(run)
    test_db.commit()
    test_db.add(
        ScriptExecution(
            backup_plan_run_id=run.id,
            hook_type="pre-backup",
            status="completed",
            started_at=datetime.utcnow(),
            triggered_by="backup_plan",
        )
    )
    test_db.commit()

    assert (backup.id, repository.id, "pending") not in _boot(test_db)


def test_an_old_backup_the_restart_failed_is_left_alone(test_db):
    # failed by a restart before this existed: no line says its hooks are due
    repository = _repository(test_db)
    _backup(
        test_db,
        repository,
        ("pre-backup", None),
        status="failed",
        error="interrupted by restart",
    )

    assert _boot(test_db) == []


def test_a_second_restart_before_the_post_hooks_started_finds_them_again(test_db):
    repository = _repository(test_db)
    backup = _backup(
        test_db,
        repository,
        ("pre-backup", None),
        status="failed",
        error="\n".join(["interrupted by restart", BACKUP_POST_HOOKS_AFTER_RESTART]),
    )

    assert _boot(test_db) == [(backup.id, repository.id, "pending")]


@pytest.mark.asyncio
async def test_a_second_restart_after_the_post_hooks_started_reports_them_once(
    test_db,
):
    # the recovered hooks were interrupted: not run again, but reported
    repository = _repository(test_db)
    backup = _backup(
        test_db,
        repository,
        ("pre-backup", None),
        ("post-backup", None),
        status="failed",
        error="\n".join(["interrupted by restart", BACKUP_POST_HOOKS_AFTER_RESTART]),
    )
    scripts = _Scripts(test_db)

    found = _boot(test_db)
    assert found == [(backup.id, repository.id, "interrupted")]
    notify = await _recover(test_db, found, scripts)

    assert scripts.calls == []
    notify.assert_awaited_once()
    assert _boot(test_db) == []


# --- running them after the restart -----------------------------------------


@pytest.mark.asyncio
async def test_post_hooks_run_after_the_restart_as_failure(test_db):
    repository = _repository(
        test_db,
        post=(("start-db", "failure"), ("report", "success"), ("cleanup", "always")),
    )
    backup = _backup(test_db, repository, ("pre-backup", None))
    scripts = _Scripts(test_db)

    notify = await _recover(test_db, _boot(test_db), scripts)

    assert scripts.calls == [("start-db", "failure"), ("cleanup", "failure")]
    stored = test_db.get(Operation, backup.id)
    assert stored.status == "failed"
    assert stored.error_message == "interrupted by restart"
    notify.assert_not_awaited()
    rows = (
        test_db.query(ScriptExecution)
        .filter(
            ScriptExecution.operation_id == backup.id,
            ScriptExecution.hook_type == "post-backup",
        )
        .count()
    )
    assert rows == 2


@pytest.mark.asyncio
async def test_failing_post_hook_after_the_restart_needs_attention(test_db):
    repository = _repository(test_db)
    backup = _backup(test_db, repository, ("pre-backup", None))
    scripts = _Scripts(test_db, fail={"start-db"})

    notify = await _recover(test_db, _boot(test_db), scripts)

    assert _keys(_lines(test_db, backup.id)) == [
        "interrupted by restart",
        MARKER_KEY,
        "backend.errors.service.postBackupHooksAlsoFailed",
    ]
    notify.assert_awaited_once()
    assert notify.await_args.args[1] == "/backups/db-host"
    assert notify.await_args.args[3] == backup.id
    # a sentence, not the row's message keys
    assert notify.await_args.args[2] == (
        "Post-backup hooks after the restart did not run cleanly: 1/2 "
        "post-backup scripts failed. Check what the pre-backup hooks stopped."
    )


def test_the_sweep_marks_the_backup_before_the_runner_fails_it(test_db):
    # in the sweep's own commit: a restart before the post-backup hooks
    # start finds the backup again
    repository = _repository(test_db)
    backup = _backup(test_db, repository, ("pre-backup", None))

    backup_post_hooks_after_restart(test_db)
    test_db.expire_all()
    stored = test_db.get(Operation, backup.id)
    assert (stored.status, stored.error_message) == (
        "running",
        BACKUP_POST_HOOKS_AFTER_RESTART,
    )

    with patch.object(operation_runner, "_recover_repository_lock"):
        operation_runner.recover_on_startup(test_db)
    test_db.expire_all()
    assert _keys(_lines(test_db, backup.id)) == ["interrupted by restart", MARKER_KEY]


def test_a_restart_right_after_the_runner_failed_the_backup_finds_it_again(
    test_db,
):
    repository = _repository(test_db)
    backup = _backup(test_db, repository, ("pre-backup", None))
    _boot(test_db)  # no task got to run its post-backup hooks

    assert _boot(test_db) == [(backup.id, repository.id, "pending")]
    assert _keys(_lines(test_db, backup.id)) == ["interrupted by restart", MARKER_KEY]


@pytest.mark.asyncio
async def test_interrupted_post_hooks_are_reported_not_run_again(test_db):
    repository = _repository(test_db)
    backup = _backup(test_db, repository, ("pre-backup", None), ("post-backup", None))
    scripts = _Scripts(test_db)

    notify = await _recover(test_db, _boot(test_db), scripts)

    assert scripts.calls == []
    assert _keys(_lines(test_db, backup.id)) == ["interrupted by restart", MARKER_KEY]
    notify.assert_awaited_once()


@pytest.mark.asyncio
async def test_a_deleted_repository_after_the_restart_needs_attention(test_db):
    repository = _repository(test_db)
    backup = _backup(test_db, repository, ("pre-backup", None))
    found = _boot(test_db)
    test_db.get(Operation, backup.id).repository_id = None
    test_db.commit()

    notify = await _recover(test_db, found, _Scripts(test_db))

    assert _lines(test_db, backup.id) == [
        "interrupted by restart",
        BACKUP_POST_HOOKS_AFTER_RESTART,
        "Repository no longer exists",
    ]
    notify.assert_awaited_once()


@pytest.mark.asyncio
async def test_post_hooks_wait_for_the_interrupted_backup_to_end(test_db):
    repository = _repository(test_db)
    backup = _backup(test_db, repository, ("pre-backup", None))
    found = backup_post_hooks_after_restart(test_db)
    order = []

    async def wait_out(operation_id, **kwargs):
        order.append(("backup ended", operation_id))
        with patch.object(operation_runner, "_recover_repository_lock"):
            operation_runner.recover_on_startup(test_db)
        return "failed"

    async def script(*args, **kwargs):
        order.append(("script", None))
        return {"success": True, "exit_code": 0, "stdout": "", "stderr": ""}

    with patch(
        "app.services.backup_service.wait_out_backup_operation",
        side_effect=wait_out,
    ):
        await _recover(test_db, found, script)

    assert order[0] == ("backup ended", backup.id)
    assert ("script", None) in order[1:]
    assert test_db.get(Operation, backup.id).error_message == "interrupted by restart"


# --- what waits for them ------------------------------------------------------


@pytest.mark.asyncio
async def test_recovery_tasks_are_tracked_until_they_end(test_db):
    release = asyncio.Event()

    async def post_hooks(operation_id, state):
        await release.wait()

    with patch.object(backup_service, "_post_hooks_after_restart", new=post_hooks):
        backup_service.recover_post_hooks_after_restart([(7, 3, "pending")])
        assert 7 in backup_service.post_hooks_after_restart
        waiter = asyncio.create_task(
            backup_service.wait_for_post_hooks_after_restart(repository_id=3)
        )
        other = asyncio.create_task(
            backup_service.wait_for_post_hooks_after_restart(repository_id=4)
        )
        await asyncio.sleep(0)
        assert not waiter.done()
        await other
        release.set()
        await waiter
        await asyncio.sleep(0)

    assert 7 not in backup_service.post_hooks_after_restart


@pytest.mark.asyncio
async def test_a_cancelled_waiter_leaves_the_post_hooks_running(test_db):
    release = asyncio.Event()

    async def post_hooks(operation_id, state):
        await release.wait()

    with patch.object(backup_service, "_post_hooks_after_restart", new=post_hooks):
        backup_service.recover_post_hooks_after_restart([(8, 3, "pending")])
        _repo_id, task = backup_service.post_hooks_after_restart[8]
        waiter = asyncio.create_task(
            backup_service.wait_for_post_hooks_after_restart(operation_id=8)
        )
        await asyncio.sleep(0)
        waiter.cancel()
        await asyncio.sleep(0)
        assert not task.done()
        release.set()
        await task


def test_startup_launches_the_backup_recovery_before_the_plan_recovery(test_db):
    from app.main import _recover_interrupted_work
    from app.services.backup_plan_execution_service import (
        backup_plan_execution_service,
    )

    repository = _repository(test_db)
    backup = _backup(test_db, repository, ("pre-backup", None))
    order = []
    with (
        patch.object(
            backup_service,
            "recover_post_hooks_after_restart",
            side_effect=lambda found: order.append(("backups", found)),
        ),
        patch.object(
            backup_plan_execution_service,
            "recover_post_hooks_after_restart",
            side_effect=lambda found: order.append(("plans", found)),
        ),
    ):
        _recover_interrupted_work()

    assert order == [
        ("backups", [(backup.id, repository.id, "pending")]),
        ("plans", []),
    ]


@pytest.mark.asyncio
async def test_a_new_backup_waits_before_its_pre_hooks(tmp_path):
    # its pre-backup hooks must not stop what the recovered post-backup
    # hooks start again
    from tests.unit.test_backup_post_hooks_on_early_exit import (
        _hooks,
        _job,
        _repo,
        _run,
    )

    release = asyncio.Event()
    order = []

    async def post_hooks(operation_id, state):
        await release.wait()
        order.append("recovered post-hooks ended")

    hooks = _hooks()
    original = hooks.side_effect

    async def execute_hooks(**kwargs):
        order.append(kwargs["hook_type"])
        return await original(**kwargs)

    hooks.side_effect = execute_hooks
    job = _job(id=1429, status="pending")
    repo = _repo(str(tmp_path / "gone"))
    with patch.object(backup_service, "_post_hooks_after_restart", new=post_hooks):
        backup_service.recover_post_hooks_after_restart([(99, repo.id, "pending")])
        backup = asyncio.create_task(_run(backup_service, job, repo, hooks))
        for _ in range(5):
            await asyncio.sleep(0)
        assert order == []
        release.set()
        await backup

    assert order[:2] == ["recovered post-hooks ended", "pre-backup"]


@pytest.mark.asyncio
async def test_a_plan_run_waits_for_its_backups_post_hooks(test_db):
    from app.services.backup_plan_execution_service import (
        backup_plan_execution_service,
    )

    order = []

    async def wait_out(operation_id, **kwargs):
        order.append(("backup ended", operation_id))
        return "failed"

    async def wait_for(**kwargs):
        order.append(("backup post-hooks ended", kwargs.get("operation_id")))

    async def post_scripts(run_id, context, backup_result):
        order.append(("plan post-scripts", None))
        return []

    with (
        patch.object(
            backup_plan_execution_service, "_restart_context", return_value=object()
        ),
        patch.object(
            backup_plan_execution_service,
            "_run_backup_operation_ids",
            return_value=[41],
        ),
        patch.object(
            backup_plan_execution_service, "_pre_backup_agent_job_ids", return_value=[]
        ),
        patch.object(
            backup_plan_execution_service,
            "_wait_for_agent_job_to_end",
            new=AsyncMock(),
        ),
        patch(
            "app.services.backup_plan_execution_service.wait_out_backup_operation",
            side_effect=wait_out,
        ),
        patch.object(
            backup_service, "wait_for_post_hooks_after_restart", side_effect=wait_for
        ),
        patch.object(
            backup_plan_execution_service,
            "_run_post_backup_scripts",
            side_effect=post_scripts,
        ),
        patch.object(
            backup_plan_execution_service,
            "_settle_post_hooks_after_restart",
            new=AsyncMock(),
        ),
    ):
        await backup_plan_execution_service._run_post_hooks_after_restart(5)

    assert order == [
        ("backup ended", 41),
        ("backup post-hooks ended", 41),
        ("plan post-scripts", None),
    ]


# --- a backup that wrote its outcome before its post-backup hooks -------------


def test_a_completed_backup_that_never_reached_its_end_is_found(test_db):
    # `completed` and `completed_at` are committed before the archive
    # statistics and the post-backup hooks; the runner's `result` after them
    repository = _repository(test_db)
    backup = _backup(
        test_db, repository, ("pre-backup", None), status="completed", ended=False
    )

    assert _boot(test_db) == [(backup.id, repository.id, "pending")]
    assert test_db.get(Operation, backup.id).status == "completed"


def test_an_unended_backup_with_a_later_backup_is_left_alone(test_db):
    # the later backup's own hooks ran since
    repository = _repository(test_db)
    _backup(test_db, repository, ("pre-backup", None), status="completed", ended=False)
    _backup(test_db, repository, status="completed")

    assert _boot(test_db) == []


def test_a_cancelled_backup_is_not_looked_at(test_db):
    # the cancel route writes `completed_at` itself (a known limit)
    repository = _repository(test_db)
    _backup(test_db, repository, ("pre-backup", None), status="cancelled")

    assert _boot(test_db) == []


@pytest.mark.asyncio
async def test_a_completed_backup_runs_its_post_hooks_as_success(test_db):
    repository = _repository(
        test_db,
        post=(("start-db", "failure"), ("report", "success"), ("cleanup", "always")),
    )
    backup = _backup(
        test_db, repository, ("pre-backup", None), status="completed", ended=False
    )
    scripts = _Scripts(test_db)

    notify = await _recover(test_db, _boot(test_db), scripts)

    assert scripts.calls == [("report", "success"), ("cleanup", "success")]
    stored = test_db.get(Operation, backup.id)
    assert (stored.status, stored.error_message) == ("completed", None)
    notify.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_completed_backup_whose_post_hooks_fail_is_a_warning(test_db):
    repository = _repository(test_db, post=(("report", "success"),))
    backup = _backup(
        test_db, repository, ("pre-backup", None), status="completed", ended=False
    )

    notify = await _recover(test_db, _boot(test_db), _Scripts(test_db, fail={"report"}))

    stored = test_db.get(Operation, backup.id)
    assert stored.status == "completed_with_warnings"
    assert _keys(stored.error_message.split("\n")) == [
        MARKER_KEY,
        "backend.errors.service.postBackupHooksAlsoFailed",
    ]
    notify.assert_awaited_once()


# --- an inline post-backup script --------------------------------------------


@pytest.mark.asyncio
async def test_an_inline_post_script_is_not_run_again_but_reported(test_db):
    # it leaves no record, so whether it already ran cannot be told
    repository = _repository(test_db, post=())
    repository.post_backup_script = "systemctl start db"
    test_db.commit()
    backup = _backup(test_db, repository, ("pre-backup", None))
    inline = AsyncMock()

    with patch.object(backup_service, "_execute_hooks", new=inline):
        notify = await _recover(test_db, _boot(test_db), _Scripts(test_db))

    inline.assert_not_awaited()
    assert _keys(_lines(test_db, backup.id)) == ["interrupted by restart", MARKER_KEY]
    notify.assert_awaited_once()
    assert "inline post-backup script" in notify.await_args.args[2]


@pytest.mark.asyncio
async def test_no_post_hooks_at_all_settles_the_backup(test_db):
    repository = _repository(test_db, post=())
    backup = _backup(test_db, repository, ("pre-backup", None))

    notify = await _recover(test_db, _boot(test_db), _Scripts(test_db))

    assert test_db.get(Operation, backup.id).error_message == "interrupted by restart"
    notify.assert_not_awaited()


def test_the_runner_keeps_the_lines_a_sweep_wrote(test_db):
    repository = _repository(test_db)
    backup = _backup(test_db, repository, error="sweep line")

    with patch.object(operation_runner, "_recover_repository_lock"):
        operation_runner.recover_on_startup(test_db)
    test_db.expire_all()

    assert _lines(test_db, backup.id) == ["interrupted by restart", "sweep line"]


@pytest.mark.asyncio
async def test_a_backup_without_hooks_waits_too(tmp_path):
    # skip_hooks: it does not stop what the recovered hooks start, but it
    # must not read the files while they start it either
    from tests.unit.test_backup_post_hooks_on_early_exit import (
        _hooks,
        _job,
        _repo,
        _run,
    )

    release = asyncio.Event()
    order = []

    async def post_hooks(operation_id, state):
        await release.wait()
        order.append("recovered post-hooks ended")

    job = _job(id=1431, status="pending")
    repo = _repo(str(tmp_path / "gone"))
    with patch.object(backup_service, "_post_hooks_after_restart", new=post_hooks):
        backup_service.recover_post_hooks_after_restart([(98, repo.id, "pending")])
        backup = asyncio.create_task(
            _run(
                backup_service,
                job,
                repo,
                _hooks(),
                patch.object(
                    backup_service,
                    "_validate_local_source_paths_exist",
                    side_effect=lambda *a, **k: order.append("backup goes on"),
                ),
                skip_hooks=True,
            )
        )
        for _ in range(5):
            await asyncio.sleep(0)
        assert order == []
        release.set()
        await backup

    assert order[:2] == ["recovered post-hooks ended", "backup goes on"]


@pytest.mark.asyncio
async def test_a_multi_repo_schedule_waits_before_its_backups(test_db):
    from app.api import schedule as schedule_api
    from app.database.models import ScheduledJob, ScheduledJobRepository

    repository = _repository(test_db)
    schedule = ScheduledJob(
        name="nightly",
        cron_expression="0 2 * * *",
        enabled=True,
        run_repository_scripts=True,
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
    order = []

    async def wait_for(**kwargs):
        order.append(("wait", kwargs.get("repository_id")))

    # no runner runs here: stand in for the verdict it would write
    async def complete(db, operation_id, **kwargs):
        order.append(("backup", operation_id))
        db.get(Operation, operation_id).status = "completed"
        db.commit()
        return "completed"

    with (
        patch.object(
            backup_service, "wait_for_post_hooks_after_restart", side_effect=wait_for
        ),
        patch(
            "app.services.operations.backup_facade.wait_for_backup_operation",
            new=complete,
        ),
    ):
        await asyncio.wait_for(
            schedule_api.execute_multi_repo_schedule(schedule, test_db), 30
        )

    assert order[0] == ("wait", repository.id)
    assert order[1][0] == "backup"


@pytest.mark.asyncio
async def test_a_recovered_completed_backup_is_not_found_again(test_db):
    repository = _repository(test_db, post=(("report", "success"),))
    backup = _backup(
        test_db, repository, ("pre-backup", None), status="completed", ended=False
    )
    await _recover(test_db, _boot(test_db), _Scripts(test_db))

    assert _boot(test_db) == []
    stored = test_db.get(Operation, backup.id)
    assert stored.status == "completed"
    assert "archive_name" in stored.result


def test_a_backup_copied_from_the_legacy_table_is_left_alone(test_db):
    # the legacy table had no result to copy
    repository = _repository(test_db)
    backup = _backup(
        test_db,
        repository,
        ("pre-backup", None),
        ("post-backup", None),
        status="completed",
        ended=False,
    )
    backup.params = {**(backup.params or {}), "legacy_id": 7}
    test_db.commit()

    assert _boot(test_db) == []


@pytest.mark.asyncio
async def test_a_plan_run_waits_before_its_pre_scripts(test_db):
    from app.services.backup_plan_execution_service import (
        backup_plan_execution_service,
    )
    from tests.unit.test_api_backup_plans import _create_execution_plan

    repository = _repository(test_db)
    _plan, run = _create_execution_plan(test_db, [repository])
    order = []

    async def wait_for(**kwargs):
        order.append(("wait", kwargs.get("repository_id")))

    async def pre_hooks(run_id, context, *, hook_type, backup_result=None):
        order.append(("plan pre-scripts", hook_type))
        raise RuntimeError("stop here")

    with (
        patch.object(
            backup_service, "wait_for_post_hooks_after_restart", side_effect=wait_for
        ),
        patch.object(
            backup_plan_execution_service,
            "_execute_plan_script_hooks",
            side_effect=pre_hooks,
        ),
        patch.object(notification_service, "send_backup_failure", new=AsyncMock()),
    ):
        await backup_plan_execution_service.execute_run(run.id)

    assert order[:2] == [
        ("wait", repository.id),
        ("plan pre-scripts", "pre-backup"),
    ]


# --- hooks that already ran, and backups reported once ----------------------


def _ran(test_db, backup, name, status="completed"):
    """A post-backup script execution of the library script `name`."""
    script = test_db.query(Script).filter(Script.name == name).one()
    test_db.add(
        ScriptExecution(
            script_id=script.id,
            repository_id=backup.repository_id,
            operation_id=backup.id,
            hook_type="post-backup",
            status=status,
            started_at=datetime.utcnow(),
            triggered_by="backup",
        )
    )
    test_db.commit()


def test_a_completed_backup_whose_post_hooks_all_ran_is_left_alone(test_db):
    # the restart came after its post-backup hooks, before the runner's result
    repository = _repository(
        test_db, post=(("report", "success"), ("start-db", "failure"))
    )
    backup = _backup(
        test_db, repository, ("pre-backup", None), status="completed", ended=False
    )
    _ran(test_db, backup, "report")

    assert _boot(test_db) == []
    stored = test_db.get(Operation, backup.id)
    assert (stored.status, stored.error_message) == ("completed", None)
    assert "archive_name" in stored.result


def test_an_interrupted_backup_whose_post_hooks_all_ran_is_left_alone(test_db):
    repository = _repository(test_db)
    backup = _backup(test_db, repository, ("pre-backup", None))
    _ran(test_db, backup, "start-db")
    _ran(test_db, backup, "cleanup")

    assert _boot(test_db) == []
    assert _lines(test_db, backup.id) == ["interrupted by restart"]


def test_a_post_hook_that_failed_is_not_settled(test_db):
    repository = _repository(test_db)
    backup = _backup(test_db, repository, ("pre-backup", None))
    _ran(test_db, backup, "start-db", status="failed")
    _ran(test_db, backup, "cleanup")

    assert _boot(test_db) == [(backup.id, repository.id, "interrupted")]


@pytest.mark.asyncio
async def test_post_hooks_another_process_ran_meanwhile_are_not_run_again(test_db):
    repository = _repository(test_db)
    backup = _backup(test_db, repository, ("pre-backup", None))
    found = backup_post_hooks_after_restart(test_db)

    async def wait_out(operation_id, **kwargs):
        # the old process ran them while this one waited
        _ran(test_db, backup, "start-db")
        _ran(test_db, backup, "cleanup")
        with patch.object(operation_runner, "_recover_repository_lock"):
            operation_runner.recover_on_startup(test_db)
        return "failed"

    scripts = _Scripts(test_db)
    with patch(
        "app.services.backup_service.wait_out_backup_operation", side_effect=wait_out
    ):
        notify = await _recover(test_db, found, scripts)

    assert scripts.calls == []
    assert _lines(test_db, backup.id) == ["interrupted by restart"]
    notify.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_backup_reported_once_is_not_reported_again(test_db):
    # an inline post-backup script cannot be told to have run: reported once
    repository = _repository(test_db, post=())
    repository.post_backup_script = "systemctl start db"
    test_db.commit()
    backup = _backup(test_db, repository, ("pre-backup", None))
    notify = await _recover(test_db, _boot(test_db), _Scripts(test_db))
    notify.assert_awaited_once()

    assert _boot(test_db) == []
    assert _keys(_lines(test_db, backup.id)) == ["interrupted by restart", MARKER_KEY]


@pytest.mark.asyncio
async def test_a_deleted_repository_is_reported_once(test_db):
    repository = _repository(test_db)
    backup = _backup(test_db, repository, ("pre-backup", None))
    found = _boot(test_db)
    test_db.get(Operation, backup.id).repository_id = None
    test_db.commit()
    await _recover(test_db, found, _Scripts(test_db))

    assert _boot(test_db) == []


def test_a_marked_backup_whose_recovered_hooks_all_ran_loses_its_line(test_db):
    # the recovery ran them all and was cut off before it cleared the line
    repository = _repository(test_db)
    backup = _backup(
        test_db,
        repository,
        ("pre-backup", None),
        status="failed",
        error="\n".join(["interrupted by restart", BACKUP_POST_HOOKS_AFTER_RESTART]),
    )
    _ran(test_db, backup, "start-db")
    _ran(test_db, backup, "cleanup")

    assert _boot(test_db) == []
    assert _lines(test_db, backup.id) == ["interrupted by restart"]
    assert _boot(test_db) == []
