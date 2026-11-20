"""Manage: SSH keys, connections and host keys (plan phase 4, Task 5)."""

import pytest
from pydantic import ValidationError

from app.mcp.registry import REGISTRY
from tests.unit.mcp.test_tools_stubbed import run

PUBLIC = "ssh-ed25519 AAAAC3EXAMPLEpublickey borg-ui"
SYSTEM_KEY = {
    "id": 1,
    "name": "System key",
    "is_system_key": True,
    "public_key": PUBLIC,
}
KEYS = {"/api/ssh-keys": {"ssh_keys": [SYSTEM_KEY]}}
CONN = {"id": 4, "host": "backups.example.com", "username": "borg", "port": 22}
CONNS = {"/api/ssh-keys/connections": {"connections": [CONN]}}


@pytest.mark.unit
def test_generate_ssh_key_shows_public_key_only():
    routes = {
        **KEYS,
        "POST /api/ssh-keys/generate": {
            "success": True,
            "ssh_key": {"id": 2, "name": "Offsite", "public_key": PUBLIC},
        },
    }
    result, api = run("generate_ssh_key", routes, name="Offsite")
    assert api.posts[0][1]["system_key"] is False  # a system key already exists
    assert api.posts[0][1]["key_type"] == "ed25519"
    assert PUBLIC in result.text
    assert "PRIVATE KEY" not in result.text


@pytest.mark.unit
def test_add_ssh_connection_with_key_already_there():
    routes = {
        **KEYS,
        "POST /api/ssh-keys/1/test-connection": {
            "success": True,
            "connection": {**CONN, "status": "connected"},
        },
    }
    result, api = run(
        "add_ssh_connection", routes, host="backups.example.com", username="borg"
    )
    assert api.posts == [
        (
            "/api/ssh-keys/1/test-connection",
            {"host": "backups.example.com", "username": "borg", "port": 22},
        )
    ]
    assert not result.is_error
    assert result.data["connection_id"] == 4


@pytest.mark.unit
def test_add_ssh_connection_auth_failure_hands_off():
    routes = {
        **KEYS,
        "POST /api/ssh-keys/1/test-connection": {
            "success": False,
            "connection": {
                **CONN,
                "status": "failed",
                "error_message": "Permission denied",
            },
        },
    }
    result, _ = run(
        "add_ssh_connection",
        routes,
        host="backups.example.com",
        username="borg",
        port=23,
    )
    assert PUBLIC in result.text
    assert "authorized_keys" in result.text
    assert (
        "/ssh-connections?deploy=1&host=backups.example.com&username=borg&port=23"
        in (result.text)
    )
    assert "password=" not in result.text


@pytest.mark.unit
def test_add_ssh_connection_takes_no_password():
    with pytest.raises(ValidationError):
        REGISTRY["add_ssh_connection"].input_model(
            host="backups.example.com", username="borg", password="x"
        )


@pytest.mark.unit
def test_update_ssh_connection_sends_only_allowlisted_fields():
    from app.mcp.tools.manage_connections import UPDATE_SSH_FIELDS

    routes = {**CONNS, "PUT /api/ssh-keys/connections/4": {"success": True}}
    _, api = run(
        "update_ssh_connection",
        routes,
        ssh_connection="borg@backups.example.com",
        default_path="/backups",
        use_sudo=True,
    )
    assert api.puts == [
        ("/api/ssh-keys/connections/4", {"default_path": "/backups", "use_sudo": True})
    ]
    assert {"host", "username", "ssh_key_id"}.isdisjoint(UPDATE_SSH_FIELDS)


@pytest.mark.unit
@pytest.mark.parametrize("field", ["host", "username", "ssh_key_id"])
def test_update_ssh_connection_rejects_kept_out_fields(field):
    with pytest.raises(ValidationError):
        REGISTRY["update_ssh_connection"].input_model(
            ssh_connection="borg@backups.example.com", **{field: "x"}
        )


# PR #1585 review


@pytest.mark.unit
def test_add_ssh_connection_hand_off_carries_a_chosen_key():
    extra = {"id": 5, "name": "Offsite", "is_system_key": False, "public_key": PUBLIC}
    routes = {
        "/api/ssh-keys": {"ssh_keys": [SYSTEM_KEY, extra]},
        "POST /api/ssh-keys/5/test-connection": {
            "success": False,
            "connection": {**CONN},
        },
    }
    result, _ = run(
        "add_ssh_connection",
        routes,
        host="backups.example.com",
        username="borg",
        ssh_key="Offsite",
    )
    assert "ssh_key_id=5" in result.text
