"""Post-backup hooks on the ways out of a server backup before `borg create`
ends (#1385).

Once a pre-backup hook ran, every way out of `BackupService.execute_backup`
runs the post-backup hooks once, with the failure result, the way the failure
after `borg create` runs them (#85): what a pre-backup hook stopped is started
again.
"""

import json
from contextlib import ExitStack
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.database.models import (
    Operation,
    Repository,
    RepositoryScript,
    SystemSettings,
)
from app.services.backup_service import BackupService

from tests.unit.test_backup_service_mocks import (
    _mock_backup_job,
    _notification_service_mock,
)

PRE_OK = {
    "success": True,
    "execution_logs": ["pre: stopped the database"],
    "scripts_executed": 1,
    "scripts_failed": 0,
    "using_library": True,
}
POST_OK = {
    "success": True,
    "execution_logs": ["post: started the database"],
    "scripts_executed": 1,
    "scripts_failed": 0,
    "using_library": True,
}
NOTHING_RAN = {
    "success": True,
    "execution_logs": [],
    "scripts_executed": 0,
    "scripts_failed": 0,
    "using_library": False,
}


@pytest.fixture
def service():
    with patch("app.services.backup_service.settings") as conf:
        conf.data_dir = "/tmp/borg-data"
        conf.backup_timeout = 3600
        conf.script_timeout = 60
        conf.borg_info_timeout = 60
        conf.borg_list_timeout = 60
        conf.source_size_timeout = 120
        yield BackupService()


def _session(job, repo):
    session = MagicMock()

    def query(model):
        m = MagicMock()
        if model == Operation:
            m.filter.return_value.first.return_value = job
        elif model == Repository:
            m.filter.return_value.first.return_value = repo
        elif model == SystemSettings:
            m.first.return_value = SystemSettings()
        elif model == RepositoryScript:
            m.filter.return_value.count.return_value = 1
        return m

    session.query.side_effect = query
    return session


def _hooks(pre=PRE_OK, post=POST_OK):
    """A stand-in for `_execute_hooks` that answers by hook type; `post` may
    be an exception to raise."""

    async def execute_hooks(**kwargs):
        if kwargs["hook_type"] == "pre-backup":
            return pre
        if isinstance(post, Exception):
            raise post
        return post

    return AsyncMock(side_effect=execute_hooks)


def _post_calls(hooks: AsyncMock) -> list:
    return [
        call
        for call in hooks.await_args_list
        if call.kwargs.get("hook_type") == "post-backup"
    ]


async def _run(service, job, repo, hooks, *patches, **kwargs):
    session = _session(job, repo)
    notifications = _notification_service_mock()
    with ExitStack() as stack:
        stack.enter_context(
            patch("app.services.backup_service.SessionLocal", return_value=session)
        )
        stack.enter_context(
            patch("app.services.backup_service.resolve_backup_job", return_value=job)
        )
        stack.enter_context(
            patch(
                "app.services.backup_service.BorgRouter.validate_local_repository_access",
                return_value=None,
            )
        )
        stack.enter_context(
            patch("app.services.backup_service.notification_service", notifications)
        )
        stack.enter_context(patch("app.services.backup_service.mqtt_service"))
        stack.enter_context(
            patch.object(
                service, "_calculate_and_update_size_background", new=AsyncMock()
            )
        )
        stack.enter_context(patch.object(service, "_execute_hooks", hooks))
        for item in patches:
            stack.enter_context(item)
        await service.execute_backup(job.id, repo.path, db=session, **kwargs)
    return notifications


def _job(**fields):
    return _mock_backup_job(logs=None, scheduled_job_id=None, **fields)


def _repo(source: str, **fields) -> Repository:
    return Repository(
        id=1385,
        path="/backups/repo",
        name="repo",
        source_directories=json.dumps([source]),
        continue_on_hook_failure=False,
        **fields,
    )


@pytest.mark.asyncio
async def test_missing_source_path_runs_post_hooks_as_failure(service, tmp_path):
    job = _job(id=1, status="pending")
    repo = _repo(str(tmp_path / "gone"))
    hooks = _hooks()

    notifications = await _run(service, job, repo, hooks)

    calls = _post_calls(hooks)
    assert len(calls) == 1
    assert calls[0].kwargs["backup_result"] == "failure"
    assert job.status == "failed"
    assert "pathNotFound" in job.error_message
    assert "post: started the database" in job.logs
    notifications.send_backup_failure.assert_awaited_once()


@pytest.mark.asyncio
async def test_prepare_source_paths_raising_runs_post_hooks_as_failure(
    service, tmp_path
):
    # e.g. the refused replacement of a staged restore canary (#1372)
    job = _job(id=2, status="pending")
    repo = _repo(str(tmp_path))
    hooks = _hooks()
    refusal = RuntimeError(
        json.dumps({"key": "backend.errors.restoreCanary.refusedReplace"})
    )

    await _run(
        service,
        job,
        repo,
        hooks,
        patch.object(service, "_prepare_source_paths", AsyncMock(side_effect=refusal)),
    )

    calls = _post_calls(hooks)
    assert len(calls) == 1
    assert calls[0].kwargs["backup_result"] == "failure"
    assert job.status == "failed"


@pytest.mark.asyncio
async def test_no_prepared_source_paths_runs_post_hooks_as_failure(service, tmp_path):
    job = _job(id=3, status="pending")
    repo = _repo(str(tmp_path))
    hooks = _hooks()

    notifications = await _run(
        service,
        job,
        repo,
        hooks,
        patch.object(
            service, "_prepare_source_paths", AsyncMock(return_value=([], []))
        ),
    )

    calls = _post_calls(hooks)
    assert len(calls) == 1
    assert calls[0].kwargs["backup_result"] == "failure"
    assert job.status == "failed"
    assert "failedPrepareSourcePaths" in job.error_message
    assert "post: started the database" in job.logs
    notifications.send_backup_failure.assert_awaited_once()


@pytest.mark.asyncio
async def test_failed_pre_hook_runs_post_hooks_as_failure(service, tmp_path):
    # a pre-backup hook that stopped a service and then exited non-zero
    job = _job(id=4, status="pending")
    repo = _repo(str(tmp_path))
    pre_failed = {**PRE_OK, "success": False, "scripts_failed": 1}
    hooks = _hooks(pre=pre_failed)

    borg = AsyncMock()
    await _run(
        service,
        job,
        repo,
        hooks,
        patch("app.services.backup_service.asyncio.create_subprocess_exec", borg),
    )

    borg.assert_not_called()
    calls = _post_calls(hooks)
    assert len(calls) == 1
    assert calls[0].kwargs["backup_result"] == "failure"
    assert job.status == "failed"
    assert "preBackupHooksFailed" in job.error_message
    assert "post: started the database" in job.logs


@pytest.mark.asyncio
async def test_cancel_while_waiting_for_the_lock_runs_post_hooks_as_failure(
    service, tmp_path
):
    job = _job(id=5, status="pending")
    repo = _repo(str(tmp_path))
    hooks = _hooks()

    def cancelled(_db, row):
        row.status = "cancelled"

    await _run(
        service,
        job,
        repo,
        hooks,
        patch(
            "app.services.backup_service.acquire_repository_command_lock",
            AsyncMock(return_value=MagicMock()),
        ),
        patch("app.services.backup_service.refresh_backup_job", cancelled),
    )

    calls = _post_calls(hooks)
    assert len(calls) == 1
    assert calls[0].kwargs["backup_result"] == "failure"
    assert job.status == "cancelled"


@pytest.mark.asyncio
async def test_failing_post_hook_is_reported_on_the_early_exit(service, tmp_path):
    job = _job(id=6, status="pending")
    repo = _repo(str(tmp_path / "gone"))
    hooks = _hooks(post={**POST_OK, "success": False, "scripts_failed": 1})

    notifications = await _run(service, job, repo, hooks)

    assert len(_post_calls(hooks)) == 1
    lines = job.error_message.split("\n")
    assert json.loads(lines[0])["key"] == "backend.errors.filesystem.pathNotFound"
    assert (
        json.loads(lines[1])["key"]
        == "backend.errors.service.postBackupHooksAlsoFailed"
    )
    notified = notifications.send_backup_failure.await_args.args[2]
    assert "postBackupHooksAlsoFailed" in notified


@pytest.mark.asyncio
async def test_post_hook_raising_on_the_early_exit_keeps_the_backup_error(
    service, tmp_path
):
    job = _job(id=7, status="pending")
    repo = _repo(str(tmp_path / "gone"))
    hooks = _hooks(post=RuntimeError("hook runner broke"))

    await _run(service, job, repo, hooks)

    assert len(_post_calls(hooks)) == 1
    assert job.status == "failed"
    lines = job.error_message.split("\n")
    assert json.loads(lines[0])["key"] == "backend.errors.filesystem.pathNotFound"
    assert (
        json.loads(lines[1])["key"]
        == "backend.errors.service.postBackupHooksAlsoFailed"
    )


@pytest.mark.asyncio
async def test_post_hooks_raising_after_borg_do_not_run_twice(service, tmp_path):
    # the exception comes from the post-backup hooks themselves
    job = _job(id=8, status="pending")
    repo = _repo(str(tmp_path))
    hooks = _hooks(post=RuntimeError("hook runner broke"))
    borg = AsyncMock()
    borg.returncode = 2
    borg.stdout = AsyncMock()
    borg.stdout.__aiter__.return_value = iter([])

    await _run(
        service,
        job,
        repo,
        hooks,
        patch(
            "app.services.backup_service.asyncio.create_subprocess_exec",
            return_value=borg,
        ),
    )

    assert len(_post_calls(hooks)) == 1
    assert job.status == "failed"


@pytest.mark.asyncio
async def test_no_post_hooks_when_no_pre_hook_ran(service, tmp_path):
    job = _job(id=9, status="pending")
    repo = _repo(str(tmp_path / "gone"))
    hooks = _hooks(pre=NOTHING_RAN)

    await _run(service, job, repo, hooks)

    assert _post_calls(hooks) == []
    assert job.status == "failed"


@pytest.mark.asyncio
async def test_no_hooks_when_the_caller_runs_them(service, tmp_path):
    # multi-repo schedules run the hooks around the backups themselves
    job = _job(id=10, status="pending")
    repo = _repo(str(tmp_path / "gone"))
    hooks = _hooks()

    await _run(service, job, repo, hooks, skip_hooks=True)

    assert hooks.await_count == 0
    assert job.status == "failed"


@pytest.mark.asyncio
async def test_skip_by_a_pre_hook_runs_no_post_hooks(service, tmp_path):
    # a graceful skip stands the backup down; it is no failure
    job = _job(id=11, status="pending")
    repo = _repo(str(tmp_path), skip_on_hook_failure=True)
    inline_failed = {
        **PRE_OK,
        "success": False,
        "scripts_failed": 1,
        "using_library": False,
    }
    hooks = _hooks(pre=inline_failed)

    await _run(service, job, repo, hooks)

    assert _post_calls(hooks) == []
    assert job.status == "skipped"


@pytest.mark.asyncio
async def test_failing_post_hook_after_a_cancel_in_the_lock_wait_is_kept(
    service, tmp_path
):
    job = _job(id=12, status="pending", error_message=None)
    repo = _repo(str(tmp_path))
    hooks = _hooks(post={**POST_OK, "success": False, "scripts_failed": 1})

    def cancelled(_db, row):
        row.status = "cancelled"

    await _run(
        service,
        job,
        repo,
        hooks,
        patch(
            "app.services.backup_service.acquire_repository_command_lock",
            AsyncMock(return_value=MagicMock()),
        ),
        patch("app.services.backup_service.refresh_backup_job", cancelled),
    )

    assert job.status == "cancelled"
    assert (
        json.loads(job.error_message)["key"]
        == "backend.errors.service.postBackupHooksAlsoFailed"
    )
