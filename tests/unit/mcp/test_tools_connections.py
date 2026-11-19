"""Connections, scripts, notifications, settings and users (plan Task 11)."""

from unittest.mock import AsyncMock, patch

import pytest

from app.database.models import McpActivity
from tests.unit.mcp.conftest import SECRET_VALUES
from tests.unit.mcp.test_tools_stubbed import run as _run


@pytest.mark.unit
def test_lists_without_secrets(admin_mcp, secrets_seeded):
    keys = admin_mcp.call("list_ssh_keys")
    assert "*nas key*: ed25519, SHA256:abc, used by 0 connections" in keys["text"]
    channels = admin_mcp.call("list_notification_channels")
    assert "*Phone* via tgram: backup failure" in channels["text"]
    remotes = admin_mcp.call("list_rclone_remotes")
    assert "✓ *b2*: b2" in remotes["text"]
    scripts = admin_mcp.call("list_scripts")
    assert "*notify*: Ping when done" in scripts["text"]
    for result in (keys, channels, remotes, scripts):
        for secret in SECRET_VALUES:
            assert secret not in str(result)


@pytest.mark.unit
def test_empty_connection_lists(admin_mcp):
    assert admin_mcp.call("list_ssh_connections")["text"] == "No SSH connections yet."
    assert admin_mcp.call("list_agents")["text"] == "No agent machines yet."


@pytest.mark.unit
def test_get_settings(admin_mcp):
    result = admin_mcp.call("get_settings")
    assert result["text"].startswith("Borg UI settings:")
    assert "Backups at once: 1" in result["text"]
    assert "webhook_url" not in str(result)


@pytest.mark.unit
def test_list_users_admin_and_viewer(admin_mcp, viewer_mcp, test_db):
    assert "*admin*: admin" in admin_mcp.call("list_users")["text"]
    denied = viewer_mcp.call("list_users")
    assert denied["is_error"] and "Admin" in denied["text"]
    test_db.expire_all()
    assert (
        test_db.query(McpActivity)
        .filter(McpActivity.tool == "list_users")
        .order_by(McpActivity.id.desc())
        .first()
        .outcome
        == "denied_rbac"
    )


@pytest.mark.unit
def test_browse_server_folders(admin_mcp, monkeypatch, tmp_path):
    (tmp_path / "photos").mkdir()
    (tmp_path / "notes.txt").write_text("x" * 10)
    result = admin_mcp.call("browse_server_folders", path=str(tmp_path))
    assert not result["is_error"], result["text"]
    assert "📁 photos/" in result["text"]
    assert "notes.txt  10 B" in result["text"]


# Phase 3, Task 8: tests, sources, background work

_SSH = {
    "id": 4,
    "host": "backups.example.com",
    "username": "borg",
    "port": 22,
    "ssh_key_id": 6,
}


@pytest.mark.unit
def test_ssh_connection_test_passes():
    routes = {
        "/api/ssh-keys/connections": {"connections": [_SSH]},
        "POST /api/ssh-keys/connections/4/test": {
            "success": True,
            "status": "connected",
            "error": None,
        },
    }
    result, api = _run(
        "test_ssh_connection", routes, connection="borg@backups.example.com"
    )
    assert api.posts == [("/api/ssh-keys/connections/4/test", None)]
    assert result.text == "✓ borg@backups.example.com answered. The connection works."


@pytest.mark.unit
def test_ssh_connection_test_fails():
    routes = {
        "/api/ssh-keys/connections": {"connections": [_SSH]},
        "POST /api/ssh-keys/connections/4/test": {
            "success": False,
            "status": "failed",
            "error": "Permission denied (publickey)",
        },
    }
    result, _ = _run(
        "test_ssh_connection", routes, connection="borg@backups.example.com"
    )
    assert result.is_error
    assert result.text.startswith(
        "✗ Could not connect to borg@backups.example.com: Permission denied (publickey)"
    )


@pytest.mark.unit
def test_notification_result_never_holds_the_url(
    mcp, create_connection, admin_headers, secrets_seeded, test_db
):
    from app.database.models import McpActivity

    sent = AsyncMock(return_value={"success": True, "message": "sent"})
    _, token = create_connection(admin_headers, name="ops", level="operate")
    with patch(
        "app.api.notifications.notification_service.test_notification", new=sent
    ):
        result = mcp(token).call("test_notification", channel="Phone")
    assert sent.await_args.args[0] == "tgram://123456:SECRET-BOT-TOKEN/987"
    assert not result["is_error"]
    assert result["text"] == "✓ Sent a test message to *Phone*."
    dumped = repr(result)
    assert "SECRET-BOT-TOKEN" not in dumped and "tgram://" not in dumped
    row = test_db.query(McpActivity).order_by(McpActivity.id.desc()).first()
    assert row.target == "notification channel Phone"
    assert "SECRET" not in (row.target or "") + (row.error_key or "")


@pytest.mark.unit
def test_notification_needs_admin(mcp, create_connection, auth_headers, secrets_seeded):
    _, token = create_connection(auth_headers, name="viewer", level="operate")
    result = mcp(token).call("test_notification", channel="Phone")
    assert result["is_error"] and "tgram" not in result["text"]
    assert "no Borg UI tool" not in result["text"]


@pytest.mark.unit
def test_script_test_shows_output_tail():
    routes = {
        "/api/scripts": [{"id": 3, "name": "notify"}],
        "POST /api/scripts/3/test": {
            "success": True,
            "stdout": "\n".join(f"out {i}" for i in range(80)),
            "stderr": "",
            "exit_code": 0,
            "execution_time": 1.2,
        },
    }
    result, api = _run("test_script", routes, script="notify")
    assert api.posts == [("/api/scripts/3/test", {})]
    assert result.text.startswith("✓ *notify* ran in 1 s and exited with 0.")
    assert "out 79" in result.text and "out 29" not in result.text


@pytest.mark.unit
def test_script_test_with_repository_context():
    routes = {
        "/api/scripts": [{"id": 3, "name": "notify"}],
        "/api/repositories/": {"repositories": [{"id": 1, "name": "Photos"}]},
        "POST /api/scripts/3/test": {
            "success": False,
            "stdout": "",
            "stderr": "boom",
            "exit_code": 2,
            "execution_time": 0.1,
        },
    }
    result, api = _run("test_script", routes, script="notify", repository="Photos")
    assert api.posts == [("/api/scripts/3/test", {"repository_id": 1})]
    assert result.is_error and result.text.startswith("✗ *notify* exited with 2")


@pytest.mark.unit
def test_script_test_needs_admin(mcp, create_connection, auth_headers, secrets_seeded):
    _, token = create_connection(auth_headers, name="viewer", level="operate")
    result = mcp(token).call("test_script", script="notify")
    assert result["is_error"]
    assert "no Borg UI tool" not in result["text"]


@pytest.mark.unit
def test_script_output_hides_the_server_environment(monkeypatch):
    """The script runs with a copy of the server's environment; whatever its
    variables are called, their values never reach the AI (spec 5.9)."""
    monkeypatch.setenv("MY_SERVICE_HANDLE", "tok_s3cr3t-value-123")
    monkeypatch.setenv("SHORTY", "abc")
    routes = {
        "/api/scripts": [{"id": 3, "name": "notify"}],
        "POST /api/scripts/3/test": {
            "success": True,
            "stdout": "MY_SERVICE_HANDLE=tok_s3cr3t-value-123\nSHORTY=abc\nhello",
            "stderr": "used tok_s3cr3t-value-123 again",
            "exit_code": 0,
            "execution_time": 0.2,
        },
    }
    result, _ = _run("test_script", routes, script="notify")
    dumped = repr(result.text) + repr(result.data)
    assert "tok_s3cr3t-value-123" not in dumped
    assert "MY_SERVICE_HANDLE=***" in result.text
    assert "SHORTY=abc" in result.text and "hello" in result.text
