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
}


def test_every_tool_has_scan_arguments():
    assert set(ARGS) == EXPECTED_TOOLS


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
    _, token = create_connection(headers, name=f"{role} scan", level="read")
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
        for name in sorted(EXPECTED_TOOLS):
            result = session.call(name, **_args(name, secrets_seeded))
            dumped = json.dumps(result)
            for secret in SECRET_VALUES:
                assert secret not in dumped, f"{name} as {role} leaked {secret}"
            assert result["text"] != GENERIC, f"{name} as {role} crashed"
