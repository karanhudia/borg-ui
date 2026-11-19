"""Connections, scripts, notifications, settings and users (plan Task 11)."""

import pytest

from app.database.models import McpActivity
from tests.unit.mcp.conftest import SECRET_VALUES


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
