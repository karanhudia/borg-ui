import pytest

from app.database.models import Repository, SSHConnection
from app.services.script_library_executor import build_script_env


@pytest.mark.unit
def test_build_script_env_returns_only_string_values():
    repository = Repository(id=7, name="Repo", path="/backups/repo")
    source_connection = SSHConnection(host="backup.example.com", port=2222, username="borg")

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

    with pytest.raises(TypeError, match="Invalid environment value for BORG_UI_BACKUP_STATUS"):
        build_script_env(
            repository=repository,
            hook_type="post-backup",
            backup_result={"status": "completed"},
            backup_job_id=42,
        )
