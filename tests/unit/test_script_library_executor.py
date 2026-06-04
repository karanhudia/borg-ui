from unittest.mock import patch

import pytest

from app.database.models import Repository, RepositoryScript, SSHConnection, Script
from app.services.script_library_executor import ScriptLibraryExecutor, build_script_env


@pytest.mark.unit
def test_build_script_env_returns_only_string_values():
    repository = Repository(id=7, name="Repo", path="/backups/repo")
    source_connection = SSHConnection(
        host="backup.example.com", port=2222, username="borg"
    )

    env = build_script_env(
        repository=repository,
        hook_type="post-backup",
        backup_result="success",
        backup_job_id=42,
        source_connection=source_connection,
    )

    assert env["BORG_UI_REPOSITORY_ID"] == "7"
    assert env["BORG_UI_REPOSITORY_NAME"] == "Repo"
    assert env["BORG_UI_REPOSITORY_PATH"] == "/backups/repo"
    assert env["BORG_UI_HOOK_TYPE"] == "post-backup"
    assert env["BORG_UI_BACKUP_STATUS"] == "success"
    assert env["BORG_UI_JOB_ID"] == "42"
    assert env["BORG_UI_SOURCE_HOST"] == "backup.example.com"
    assert env["BORG_UI_SOURCE_PORT"] == "2222"
    assert env["BORG_UI_SOURCE_USERNAME"] == "borg"
    assert all(isinstance(value, str) for value in env.values())


@pytest.mark.unit
def test_build_script_env_rejects_non_string_environment_values():
    repository = Repository(id=7, name="Repo", path="/backups/repo")

    with pytest.raises(
        TypeError, match="Invalid environment value for BORG_UI_BACKUP_STATUS"
    ):
        build_script_env(
            repository=repository,
            hook_type="post-backup",
            backup_result={"status": "completed"},
            backup_job_id=42,
        )


def _create_post_backup_script_matrix(
    db_session,
) -> tuple[Repository, dict[str, Script]]:
    repository = Repository(
        name="Matrix Repo",
        path="/backups/matrix",
        encryption="none",
        repository_type="local",
    )
    db_session.add(repository)
    db_session.commit()
    db_session.refresh(repository)

    scripts = {
        run_on: Script(
            name=f"{run_on.title()} Script",
            file_path=f"{run_on}.sh",
            category="custom",
            run_on=run_on,
        )
        for run_on in ("always", "success", "warning", "failure")
    }
    db_session.add_all(scripts.values())
    db_session.commit()

    for order, run_on in enumerate(
        ("always", "success", "warning", "failure"), start=1
    ):
        db_session.add(
            RepositoryScript(
                repository_id=repository.id,
                script_id=scripts[run_on].id,
                hook_type="post-backup",
                execution_order=order,
                enabled=True,
            )
        )
    db_session.commit()
    return repository, scripts


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("backup_result", "expected_run_on"),
    [
        ("success", {"always", "success"}),
        ("warning", {"always", "warning"}),
        ("failure", {"always", "failure"}),
    ],
)
async def test_execute_hooks_filters_post_backup_scripts_by_status(
    db_session, backup_result, expected_run_on
):
    repository, scripts = _create_post_backup_script_matrix(db_session)
    executor = ScriptLibraryExecutor(db_session)
    executed_script_ids: list[int] = []

    async def fake_execute_script_and_record(
        self, repo_script, repository, backup_job_id, hook_type, backup_result=None
    ):
        executed_script_ids.append(repo_script.script_id)
        return {"success": True, "logs": [], "exit_code": 0}

    with patch.object(
        ScriptLibraryExecutor,
        "_execute_script_and_record",
        new=fake_execute_script_and_record,
    ):
        result = await executor.execute_hooks(
            repository_id=repository.id,
            hook_type="post-backup",
            backup_result=backup_result,
            backup_job_id=42,
        )

    expected_ids = {scripts[run_on].id for run_on in expected_run_on}
    assert set(executed_script_ids) == expected_ids
    assert result["scripts_executed"] == len(expected_ids)
    assert result["scripts_failed"] == 0
    assert result["success"] is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_execute_hooks_treats_cancelled_as_failure_for_run_on_filtering(
    db_session,
):
    repository, scripts = _create_post_backup_script_matrix(db_session)
    executor = ScriptLibraryExecutor(db_session)
    executed_script_ids: list[int] = []

    async def fake_execute_script_and_record(
        self, repo_script, repository, backup_job_id, hook_type, backup_result=None
    ):
        executed_script_ids.append(repo_script.script_id)
        return {"success": True, "logs": [], "exit_code": 0}

    with patch.object(
        ScriptLibraryExecutor,
        "_execute_script_and_record",
        new=fake_execute_script_and_record,
    ):
        result = await executor.execute_hooks(
            repository_id=repository.id,
            hook_type="post-backup",
            backup_result="failure",
            backup_job_id=99,
        )

    assert set(executed_script_ids) == {scripts["always"].id, scripts["failure"].id}
    assert result["scripts_executed"] == 2
    assert result["success"] is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_execute_inline_script_injects_repository_parameter_values(db_session):
    repository = Repository(
        id=7,
        name="Repo",
        path="/backups/repo",
        pre_backup_script_parameters={"TARGET_DIR": "/srv/data", "RETRIES": 3},
        post_backup_script_parameters={"RESULT_PATH": "/tmp/out"},
    )
    executor = ScriptLibraryExecutor(db_session)
    captured = {}

    async def fake_execute_script(script, timeout, env, context):
        captured["script"] = script
        captured["timeout"] = timeout
        captured["env"] = env
        captured["context"] = context
        return {"success": True, "exit_code": 0, "stdout": "", "stderr": ""}

    with patch(
        "app.services.script_library_executor.execute_script", new=fake_execute_script
    ):
        result = await executor.execute_inline_script(
            script_content="echo test",
            script_type="pre-backup",
            timeout=30,
            repository=repository,
            backup_job_id=11,
            backup_result=None,
        )

    assert result["success"] is True
    assert captured["script"] == "echo test"
    assert captured["timeout"] == 30.0
    assert captured["context"] == "repo:7:inline:pre-backup"
    assert captured["env"]["TARGET_DIR"] == "/srv/data"
    assert captured["env"]["RETRIES"] == "3"
    assert "RESULT_PATH" not in captured["env"]
