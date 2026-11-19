"""Backup plan and schedule tools (plan Task 11)."""

import pytest

from tests.unit.mcp.test_tools_stubbed import run as _run


@pytest.mark.unit
def test_empty_states(admin_mcp):
    assert admin_mcp.call("list_backup_plans")["text"] == "No backup plans yet."
    assert admin_mcp.call("list_schedules")["text"] == "No schedules yet."


@pytest.mark.unit
def test_list_and_get_backup_plan(admin_mcp, secrets_seeded):
    listed = admin_mcp.call("list_backup_plans")
    assert listed["text"].splitlines()[0] == "1 backup plan:"
    assert (
        "*Nightly photos*: /local/photos to 0 repositories, `0 2 * * *` (UTC)"
        in listed["text"]
    )
    plan = admin_mcp.call("get_backup_plan", plan="nightly")
    assert plan["text"].startswith("*Nightly photos*")
    assert "Backs up: /local/photos" in plan["text"]
    assert "Keeps: 7d 4w 6m 1y" in plan["text"]
    runs = admin_mcp.call("list_plan_runs", plan="Nightly photos")
    assert runs["text"] == "*Nightly photos* has not run yet."


@pytest.mark.unit
def test_list_and_get_schedule(admin_mcp, secrets_seeded):
    listed = admin_mcp.call("list_schedules")
    assert "*Nightly*" in listed["text"] and "`0 3 * * *` (UTC)" in listed["text"]
    one = admin_mcp.call("get_schedule", schedule="Nightly")
    assert one["text"].startswith("*Nightly*")
    assert "When: `0 3 * * *` (UTC)" in one["text"]


@pytest.mark.unit
def test_check_cron(admin_mcp):
    ok = admin_mcp.call("check_cron", expression="0 2 * * *", timezone="Europe/Berlin")
    assert ok["text"].startswith("✓ `0 2 * * *` is valid (Europe/Berlin). Next runs:")
    assert len(ok["data"]["next_runs"]) == 5
    short = admin_mcp.call("check_cron", expression="every night")
    assert short["is_error"] and "five fields" in short["text"]
    bad = admin_mcp.call("check_cron", expression="99 2 * * *")
    assert bad["is_error"] and bad["text"].startswith("`99 2 * * *` does not work:")


# Phase 3, Task 8: discover_sources

_DB = {
    "id": "pg",
    "engine": "postgresql",
    "display_name": "PostgreSQL",
    "detected": True,
    "source_directories": ["/var/lib/postgresql"],
    "notes": [],
}
_CONTAINER = {
    "id": "c1",
    "name": "immich_postgres",
    "image": "postgres:16",
    "state": "running",
    "export_path": "/x",
    "notes": [],
    "mounts": [],
}


@pytest.mark.unit
def test_discover_sources_on_the_server():
    routes = {
        "POST /api/source-discovery/databases/scan": {
            "detections": [_DB],
            "templates": [],
            "warnings": [],
        },
        "POST /api/source-discovery/containers/scan": {
            "containers": [_CONTAINER],
            "warnings": [],
        },
    }
    result, api = _run("discover_sources", routes)
    db_body = dict(api.posts)["/api/source-discovery/databases/scan"]
    assert (
        db_body["source_type"] == "local"
        and db_body["source_ssh_connection_id"] is None
    )
    assert "/var/lib/postgresql" in db_body["paths"]
    assert dict(api.posts)["/api/source-discovery/containers/scan"] == {
        "source_type": "local",
        "source_ssh_connection_id": None,
    }
    assert result.text.startswith("Found 1 database and 1 container on this server.")
    assert "- PostgreSQL in /var/lib/postgresql" in result.text
    assert "- *immich_postgres* (postgres:16, running)" in result.text


@pytest.mark.unit
def test_discover_containers_over_ssh():
    routes = {
        "/api/ssh-keys/connections": {
            "connections": [
                {"id": 4, "host": "nas.example.com", "username": "borg", "port": 22}
            ]
        },
        "POST /api/source-discovery/containers/scan": {
            "containers": [],
            "warnings": [{"message": "docker not found"}],
        },
    }
    result, api = _run(
        "discover_sources", routes, kind="containers", connection="borg@nas.example.com"
    )
    assert api.posts == [
        (
            "/api/source-discovery/containers/scan",
            {"source_type": "remote", "source_ssh_connection_id": 4},
        )
    ]
    assert result.text.startswith("Found nothing on borg@nas.example.com.")
    assert "⚠ docker not found" in result.text


@pytest.mark.unit
def test_source_scans_wait_long():
    from app.mcp.client import LONG_TIMEOUT

    routes = {
        "POST /api/source-discovery/databases/scan": {"detections": [], "warnings": []},
        "POST /api/source-discovery/containers/scan": {
            "containers": [],
            "warnings": [],
        },
    }
    _, api = _run("discover_sources", routes)
    assert set(api.timeouts.values()) == {LONG_TIMEOUT}
