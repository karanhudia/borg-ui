import pytest

from app.services.template_service import get_system_variables


@pytest.mark.unit
def test_get_system_variables_returns_empty_dict_when_no_inputs():
    assert get_system_variables() == {}


@pytest.mark.unit
def test_get_system_variables_includes_all_supported_fields():
    result = get_system_variables(
        repository_id=12,
        repository_name="Nightly Repo",
        repository_path="/backups/nightly",
        backup_status="completed",
        hook_type="post-backup",
        job_id=42,
        source_host="backup.example.com",
        source_port=2222,
        source_username="borg",
    )

    assert result == {
        "BORG_UI_REPOSITORY_ID": "12",
        "BORG_UI_REPOSITORY_NAME": "Nightly Repo",
        "BORG_UI_REPOSITORY_PATH": "/backups/nightly",
        "BORG_UI_BACKUP_STATUS": "completed",
        "BORG_UI_HOOK_TYPE": "post-backup",
        "BORG_UI_JOB_ID": "42",
        "BORG_UI_REMOTE_HOST": "backup.example.com",
        "BORG_UI_REMOTE_PORT": "2222",
        "BORG_UI_REMOTE_USERNAME": "borg",
    }


@pytest.mark.unit
def test_get_system_variables_skips_falsey_optional_strings_but_keeps_zero_like_ids():
    result = get_system_variables(
        repository_id=0,
        repository_name="",
        repository_path="",
        backup_status="",
        hook_type="",
        job_id=0,
        source_host="",
        source_port=0,
        source_username="",
    )

    assert result == {
        "BORG_UI_REPOSITORY_ID": "0",
        "BORG_UI_JOB_ID": "0",
        "BORG_UI_REMOTE_PORT": "0",
    }
