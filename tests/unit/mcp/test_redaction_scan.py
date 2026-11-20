"""Every tool, every role: no secrets out, no crashes (plan Task 12)."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from app.mcp.errors import GENERIC
from tests.unit.mcp.conftest import SECRET_VALUES
from tests.unit.mcp.test_contract import EXPECTED_TOOLS

ARGS = {
    "get_overview": {},
    "list_problems": {},
    "get_upcoming_runs": {},
    "get_system_info": {},
    "list_repositories": {},
    "get_repository": {"repository": "Photos"},
    "get_repository_space": {"repository": "Photos"},
    "compare_retention": {"repository": "Photos"},
    "list_archives": {"repository": "Photos"},
    "get_archive": {"repository": "Photos", "archive": "latest"},
    "browse_archive": {"repository": "Photos", "archive": "latest"},
    "search_files": {"repository": "Photos", "query": "notes"},
    "get_file_history": {"repository": "Photos", "path": "home/alex/notes.md"},
    "compare_archives": {"repository": "Photos", "archive": "latest"},
    "list_activity": {},
    "list_running_jobs": {},
    "get_job": {"job_type": "backup", "job_id": "{failed}"},
    "get_job_log": {"job_type": "backup", "job_id": "{failed}"},
    "wait_for_job": {"job_type": "backup", "job_id": "{failed}"},
    "explain_failure": {},
    "list_backup_plans": {},
    "get_backup_plan": {"plan": "Nightly photos"},
    "list_plan_runs": {"plan": "Nightly photos"},
    "list_schedules": {},
    "get_schedule": {"schedule": "Nightly"},
    "check_cron": {"expression": "0 2 * * *"},
    "browse_server_folders": {"path": "/local"},
    "browse_agent_folders": {"agent": "none", "path": "/"},
    "list_ssh_connections": {},
    "list_ssh_keys": {},
    "list_agents": {},
    "list_rclone_remotes": {},
    "list_scripts": {},
    "list_notification_channels": {},
    "get_settings": {},
    "list_users": {},
    "cancel_job": {"job_type": "backup", "job_id": "{failed}"},
    "unmount_archive": {},
    # Phase 4 (manage)
    "import_repository": {"name": "Old", "path": "/data/example/old"},
    "update_repository": {"repository": "Photos", "compression": "zstd"},
    "set_check_schedule": {"repository": "Photos", "schedule": "0 3 * * 0"},
    "set_restore_check_schedule": {"repository": "Photos", "schedule": "off"},
    "update_ssh_connection": {"ssh_connection": "nobody@nowhere", "port": 2222},
    "create_backup_plan": {},
    "update_backup_plan": {"backup_plan": "Nightly photos", "compression": "zstd"},
    "set_backup_plan_enabled": {"backup_plan": "Nightly photos", "enabled": True},
    "create_schedule": {"name": "Scan"},
    "update_schedule": {"schedule": "Nightly", "name": "Nightly two"},
    "set_schedule_enabled": {"schedule": "Nightly", "enabled": True},
    "duplicate_schedule": {"schedule": "Nightly"},
    "create_script": {"name": "scan script", "content": "echo scan"},
    "update_script": {"script": "notify", "description": "Ping after"},
    "assign_script": {"repository": "Photos", "script": "notify", "hook": "pre-backup"},
    "update_notification_channel": {
        "channel": "Phone",
        "notify_on_backup_success": True,
    },
    "update_rclone_remote": {"remote": "b2", "name": "b2-eu"},
    "upgrade_agents": {"agents": ["outdated"]},
    "update_settings": {"stats_refresh_interval_minutes": 30},
    "update_user": {"user": "testuser", "full_name": "Test User"},
    "create_user": {"username": "robin"},
}
# Tools that would launch real Borg or system work inside the test process.
# Their answers leave through the same render.finish redaction as every
# other tool; their own tests run them against canned route answers.
LAUNCHES_WORK = {
    "start_backup",
    "run_backup_plan",
    "run_schedule_now",
    "retry_job",
    "check_repository",
    "compact_repository",
    "run_restore_check",
    "refresh_repository",
    "preview_prune",
    "preview_restore",
    "restore_files",
    "mount_archive",
    "test_ssh_connection",
    "test_notification",
    "test_script",
    "discover_sources",
    "pause_background_work",
    "resume_background_work",
    "create_repository",
    "generate_ssh_key",
    "add_ssh_connection",
    "trust_host_key",
}


def test_every_tool_has_scan_arguments():
    assert set(ARGS) | LAUNCHES_WORK == EXPECTED_TOOLS
    assert not set(ARGS) & LAUNCHES_WORK


def _args(name, seeded):
    return {
        k: (seeded["failed"].id if v == "{failed}" else v)
        for k, v in ARGS[name].items()
    }


@pytest.mark.unit
@pytest.mark.parametrize("role", ["admin", "operator", "viewer"])
def test_no_secrets_and_no_crashes(
    role, secrets_seeded, mcp, create_connection, request, monkeypatch
):
    monkeypatch.setattr("app.mcp.tools.jobs.WAIT_SECONDS", 0.0)
    headers = request.getfixturevalue(
        f"{role}_headers" if role != "viewer" else "auth_headers"
    )
    _, token = create_connection(headers, name=f"{role} scan", level="manage")
    session = mcp(token)
    browse = [
        {
            "name": "Documents",
            "type": "directory",
            "size": None,
            "mtime": None,
            "path": "Documents",
        }
    ]
    with patch("app.api.browse.archive_cache.get", new=AsyncMock(return_value=browse)):
        for name in sorted(ARGS):
            result = session.call(name, **_args(name, secrets_seeded))
            dumped = json.dumps(result)
            for secret in SECRET_VALUES:
                assert secret not in dumped, f"{name} as {role} leaked {secret}"
            assert result["text"] != GENERIC, f"{name} as {role} crashed"
