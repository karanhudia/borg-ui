"""The "skip" on-failure mode of a repository pre-backup library script on a
server repository (#1427).

A failing pre-backup script marked skip_on_failure stops the scripts after
it and skips the backup, as on an agent repository; the post-backup hooks
that run "always" undo what the pre-backup scripts did.
"""

from unittest.mock import patch

import pytest

from app.database.models import Repository, RepositoryScript, Script
from app.services.backup_service import BackupService
from app.services.script_library_executor import ScriptLibraryExecutor

from tests.unit.test_backup_post_hooks_on_early_exit import (
    NOTHING_RAN,
    _hooks,
    _job,
    _post_calls,
    _repo,
    _run,
)


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


def _pre_scripts(db_session, *specs):
    """A repository with one pre-backup library script per (name,
    skip_on_failure, continue_on_error) spec, in that order."""
    repository = Repository(
        name="Skip Repo",
        path="/backups/skip",
        encryption="none",
        repository_type="local",
    )
    db_session.add(repository)
    db_session.commit()
    for order, (name, skip, continue_on_error) in enumerate(specs, start=1):
        script = Script(name=name, file_path=f"{name}.sh", category="custom")
        db_session.add(script)
        db_session.commit()
        db_session.add(
            RepositoryScript(
                repository_id=repository.id,
                script_id=script.id,
                hook_type="pre-backup",
                execution_order=order,
                enabled=True,
                skip_on_failure=skip,
                continue_on_error=continue_on_error,
            )
        )
    db_session.commit()
    return repository


def _fake_scripts(fail=()):
    ran: list[str] = []

    async def execute(
        self, repo_script, repository, backup_job_id, hook_type, backup_result=None
    ):
        name = repo_script.script.name
        ran.append(name)
        ok = name not in fail
        return {
            "success": ok,
            "logs": [f"{name} ran"],
            "exit_code": 0 if ok else 1,
        }

    return ran, patch.object(
        ScriptLibraryExecutor, "_execute_script_and_record", new=execute
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_failing_skip_script_stops_the_pre_scripts_and_asks_to_skip(
    db_session,
):
    repository = _pre_scripts(
        db_session,
        ("check-leader", True, None),
        ("stop-database", False, None),
    )
    ran, scripts = _fake_scripts(fail={"check-leader"})

    with scripts:
        result = await ScriptLibraryExecutor(db_session).execute_hooks(
            repository_id=repository.id, hook_type="pre-backup", backup_job_id=7
        )

    assert ran == ["check-leader"]
    assert result["success"] is False
    assert result["should_skip"] is True
    assert result["skip_script_name"] == "check-leader"
    assert result["scripts_executed"] == 1
    assert result["execution_logs"] == ["check-leader ran"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_skip_script_that_passes_does_not_skip(db_session):
    repository = _pre_scripts(
        db_session,
        ("check-leader", True, None),
        ("stop-database", False, None),
    )
    ran, scripts = _fake_scripts()

    with scripts:
        result = await ScriptLibraryExecutor(db_session).execute_hooks(
            repository_id=repository.id, hook_type="pre-backup", backup_job_id=7
        )

    assert ran == ["check-leader", "stop-database"]
    assert result["success"] is True
    assert not result.get("should_skip")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_skip_wins_over_continue_on_error(db_session):
    # as on an agent repository: skip_on_failure is looked at first
    repository = _pre_scripts(db_session, ("check-leader", True, True))
    ran, scripts = _fake_scripts(fail={"check-leader"})

    with scripts:
        result = await ScriptLibraryExecutor(db_session).execute_hooks(
            repository_id=repository.id, hook_type="pre-backup", backup_job_id=7
        )

    assert result["should_skip"] is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_a_failing_skip_script_after_a_failed_script_still_skips(db_session):
    repository = _pre_scripts(
        db_session,
        ("stop-database", False, False),
        ("check-leader", True, None),
    )
    ran, scripts = _fake_scripts(fail={"stop-database", "check-leader"})

    with scripts:
        result = await ScriptLibraryExecutor(db_session).execute_hooks(
            repository_id=repository.id, hook_type="pre-backup", backup_job_id=7
        )

    assert ran == ["stop-database", "check-leader"]
    assert result["should_skip"] is True
    assert result["skip_script_name"] == "check-leader"
    assert result["scripts_failed"] == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_skip_on_failure_is_ignored_for_post_backup_scripts(db_session):
    repository = _pre_scripts(db_session)
    script = Script(name="start-database", file_path="start.sh", category="custom")
    db_session.add(script)
    db_session.commit()
    db_session.add(
        RepositoryScript(
            repository_id=repository.id,
            script_id=script.id,
            hook_type="post-backup",
            execution_order=1,
            enabled=True,
            skip_on_failure=True,
            continue_on_error=False,
            custom_run_on="always",
        )
    )
    db_session.commit()
    ran, scripts = _fake_scripts(fail={"start-database"})

    with scripts:
        result = await ScriptLibraryExecutor(db_session).execute_hooks(
            repository_id=repository.id,
            hook_type="post-backup",
            backup_result="success",
            backup_job_id=7,
        )

    assert not result.get("should_skip")
    assert result["scripts_failed"] == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_execute_hooks_passes_the_skip_signal_on(db_session):
    # the seam `execute_backup` reads; the existing service test mocks it
    repository = _pre_scripts(db_session, ("check-leader", True, None))
    _ran, scripts = _fake_scripts(fail={"check-leader"})

    with scripts:
        result = await BackupService()._execute_hooks(
            db=db_session, repo_record=repository, hook_type="pre-backup", job_id=7
        )

    assert result["success"] is False
    assert result["should_skip"] is True
    assert result["skip_script_name"] == "check-leader"
    assert result["using_library"] is True


LIBRARY_SKIP = {
    "success": False,
    "should_skip": True,
    "skip_script_name": "check-leader",
    "execution_logs": ["not the leader"],
    "scripts_executed": 1,
    "scripts_failed": 0,
    "using_library": True,
}
POST_FAILED = {
    "success": False,
    "execution_logs": ["post: start failed"],
    "scripts_executed": 1,
    "scripts_failed": 1,
    "using_library": True,
}


@pytest.mark.asyncio
async def test_skipped_backup_runs_the_post_hooks_as_skipped(service, tmp_path):
    job = _job(id=1427, status="pending")
    repo = _repo(str(tmp_path))
    hooks = _hooks(pre=LIBRARY_SKIP, post=NOTHING_RAN)

    notifications = await _run(service, job, repo, hooks)

    calls = _post_calls(hooks)
    assert len(calls) == 1
    assert calls[0].kwargs["backup_result"] == "skipped"
    assert job.status == "skipped"
    assert job.error_message == "Skipped by 'check-leader'"
    notifications.send_backup_failure.assert_not_awaited()


@pytest.mark.asyncio
async def test_skip_whose_post_hooks_fail_is_a_failure(service, tmp_path):
    job = _job(id=1428, status="pending")
    repo = _repo(str(tmp_path))
    hooks = _hooks(pre=LIBRARY_SKIP, post=POST_FAILED)

    notifications = await _run(service, job, repo, hooks)

    assert len(_post_calls(hooks)) == 1
    assert job.status == "failed"
    assert "postBackupHooksAlsoFailed" in job.error_message
    assert "post: start failed" in job.logs
    notifications.send_backup_failure.assert_awaited_once()


@pytest.mark.asyncio
async def test_skip_whose_post_hooks_raise_is_a_failure_and_runs_them_once(
    service, tmp_path
):
    job = _job(id=1429, status="pending")
    repo = _repo(str(tmp_path))
    hooks = _hooks(pre=LIBRARY_SKIP, post=RuntimeError("post broke"))

    await _run(service, job, repo, hooks)

    assert len(_post_calls(hooks)) == 1
    assert job.status == "failed"
    assert "postBackupHooksAlsoFailed" in job.error_message


@pytest.mark.asyncio
async def test_inline_skip_is_unchanged(service, tmp_path):
    # Repository.skip_on_hook_failure is not part of #1427
    job = _job(id=1430, status="pending")
    repo = _repo(str(tmp_path), skip_on_hook_failure=True)
    inline_failed = {
        "success": False,
        "execution_logs": [],
        "scripts_executed": 1,
        "scripts_failed": 1,
        "using_library": False,
    }
    hooks = _hooks(pre=inline_failed)

    await _run(service, job, repo, hooks)

    assert _post_calls(hooks) == []
    assert job.status == "skipped"
