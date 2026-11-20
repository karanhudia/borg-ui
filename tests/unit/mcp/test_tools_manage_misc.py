"""Manage: scripts, notification events, cloud remotes, agents (plan phase 4, Task 7)."""

import json

import pytest
from pydantic import ValidationError

from app.database.models import McpActivity
from app.mcp.client import ApiError
from app.mcp.registry import REGISTRY
from tests.unit.mcp.test_tools_stubbed import run

SCRIPTS = {"/api/scripts": [{"id": 3, "name": "pg dump"}, {"id": 4, "name": "notify"}]}
REPOS = {
    "/api/repositories/": {
        "repositories": [
            {"id": 1, "name": "Photos", "execution_target": "local"},
            {"id": 2, "name": "Laptop", "execution_target": "agent"},
        ]
    }
}


@pytest.mark.unit
def test_create_script_posts_fields_and_echoes_content():
    content = "\n".join(f"echo {i}" for i in range(30))
    routes = {"POST /api/scripts": {"id": 9, "name": "dump"}}
    result, api = run(
        "create_script", routes, name="dump", content=content, run_on="always"
    )
    path, body = api.posts[0]
    assert path == "/api/scripts"
    assert body == {"name": "dump", "content": content, "run_on": "always"}
    assert "echo 19" in result.text and "echo 20" not in result.text


@pytest.mark.unit
def test_create_script_takes_no_parameters():
    with pytest.raises(ValidationError):
        REGISTRY["create_script"].input_model(name="x", content="y", parameters=[{}])


@pytest.mark.unit
def test_update_script_sends_changes_only():
    routes = {**SCRIPTS, "PUT /api/scripts/3": {"id": 3}}
    _, api = run("update_script", routes, script="pg dump", timeout=600)
    assert api.puts == [("/api/scripts/3", {"timeout": 600})]


@pytest.mark.unit
def test_assign_script_by_names():
    routes = {**SCRIPTS, **REPOS, "POST /api/repositories/1/scripts": {"id": 1}}
    _, api = run(
        "assign_script",
        routes,
        repository="Photos",
        script="pg dump",
        hook="pre-backup",
    )
    assert api.posts == [
        ("/api/repositories/1/scripts", {"script_id": 3, "hook_type": "pre-backup"})
    ]


@pytest.mark.unit
def test_assign_script_to_agent_repository_uses_the_agent_name():
    routes = {**REPOS, "POST /api/repositories/2/scripts": {"id": 1}}
    _, api = run(
        "assign_script",
        routes,
        repository="Laptop",
        script="backup-db",
        hook="pre-backup",
    )
    assert api.posts == [
        (
            "/api/repositories/2/scripts",
            {"agent_script_name": "backup-db", "hook_type": "pre-backup"},
        )
    ]


CHANNEL = {
    "id": 6,
    "name": "Phone",
    "service_url": "json://secret.example.invalid/abc",
    "enabled": True,
    "notify_on_backup_failure": True,
    "notify_on_backup_success": False,
}


@pytest.mark.unit
def test_update_notification_events_never_sends_the_url():
    routes = {"/api/notifications": [CHANNEL], "PUT /api/notifications/6": CHANNEL}
    result, api = run(
        "update_notification_channel",
        routes,
        channel="Phone",
        notify_on_backup_success=True,
    )
    assert api.puts == [("/api/notifications/6", {"notify_on_backup_success": True})]
    dumped = result.text + json.dumps(result.data)
    assert "secret.example.invalid" not in dumped


@pytest.mark.unit
def test_update_notification_takes_no_url():
    with pytest.raises(ValidationError):
        REGISTRY["update_notification_channel"].input_model(
            channel="Phone", service_url="json://x"
        )


@pytest.mark.unit
def test_update_notification_channel_url_never_in_activity(
    secrets_seeded, mcp, create_connection, admin_headers, test_db
):
    _, token = create_connection(admin_headers, name="manage", level="manage")
    result = mcp(token).call(
        "update_notification_channel", channel="Phone", notify_on_backup_success=True
    )
    assert not result["is_error"], result["text"]
    assert "SECRET-BOT-TOKEN" not in json.dumps(result)
    row = (
        test_db.query(McpActivity)
        .filter(McpActivity.tool == "update_notification_channel")
        .one()
    )
    assert "SECRET-BOT-TOKEN" not in repr(
        {c.name: getattr(row, c.name) for c in McpActivity.__table__.columns}
    )


REMOTE = {
    "id": 8,
    "name": "b2",
    "provider": "b2",
    "config_source": "managed",
    "redacted_config": {"account": "***", "key": "***", "hard_delete": "false"},
}


@pytest.mark.unit
def test_rclone_sensitive_key_hands_off_without_put():
    routes = {"/api/rclone/remotes": {"remotes": [REMOTE]}}
    result, api = run(
        "update_rclone_remote", routes, remote="b2", settings={"key": "new"}
    )
    assert api.puts == []
    assert "/cloud-storage?edit=8" in result.text
    assert "new" not in result.text.split("cloud-storage")[0][-20:]


@pytest.mark.unit
def test_rclone_update_keeps_redacted_values():
    routes = {
        "/api/rclone/remotes": {"remotes": [REMOTE]},
        "PUT /api/rclone/remotes/8": REMOTE,
    }
    _, api = run(
        "update_rclone_remote", routes, remote="b2", settings={"hard_delete": "true"}
    )
    assert api.puts == [
        (
            "/api/rclone/remotes/8",
            {
                "redacted_config": {
                    "account": "***",
                    "key": "***",
                    "hard_delete": "true",
                }
            },
        )
    ]


@pytest.mark.unit
def test_rclone_rename_only():
    routes = {
        "/api/rclone/remotes": {"remotes": [REMOTE]},
        "PUT /api/rclone/remotes/8": REMOTE,
    }
    _, api = run("update_rclone_remote", routes, remote="b2", name="b2-eu")
    assert api.puts == [("/api/rclone/remotes/8", {"name": "b2-eu"})]


AGENTS = {
    "/api/managed-machines/agents": [
        {
            "id": 1,
            "name": "laptop",
            "upgrade_status": "outdated",
            "agent_version": "1.0.0",
        },
        {
            "id": 2,
            "name": "nas",
            "upgrade_status": "up_to_date",
            "agent_version": "1.1.0",
        },
        {"id": 3, "name": "pi", "upgrade_status": "outdated", "agent_version": "0.9.0"},
    ]
}


@pytest.mark.unit
def test_upgrade_outdated_picks_only_outdated():
    routes = {**AGENTS, "POST /api/managed-machines/agents/upgrade": {"success": True}}
    result, api = run("upgrade_agents", routes, agents=["outdated"])
    assert api.posts == [
        ("/api/managed-machines/agents/upgrade", {"agent_machine_ids": [1, 3]})
    ]
    assert "*laptop*" in result.text and "*pi*" in result.text


@pytest.mark.unit
def test_upgrade_named_agent_already_current_posts_nothing():
    result, api = run("upgrade_agents", dict(AGENTS), agents=["nas"])
    assert api.posts == []
    assert "already" in result.text


@pytest.mark.unit
def test_create_script_refused_for_non_admin():
    routes = {
        "POST /api/scripts": ApiError(
            403, "backend.errors.settings.adminAccessRequired"
        )
    }
    with pytest.raises(ApiError):
        run("create_script", routes, name="x", content="echo")
