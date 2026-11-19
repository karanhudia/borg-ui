"""REST API for MCP connections, the admin switch and the level cap."""

from datetime import datetime, timedelta

import pytest

from app.database.models import McpActivity, SystemSettings
from app.mcp.levels import Level

BASE = "/api/settings/mcp"


def _cap(test_db, level):
    settings = test_db.query(SystemSettings).first()
    if settings is None:
        settings = SystemSettings()
        test_db.add(settings)
    settings.mcp_max_access_level = level
    test_db.commit()


@pytest.mark.unit
def test_create_returns_token_once(test_client, admin_headers, create_connection):
    row, token = create_connection(admin_headers, level="operate")
    assert token.startswith("borgui_")
    assert row["access_level"] == "operate"
    assert row["effective_level"] == "operate"
    listed = test_client.get(f"{BASE}/connections", headers=admin_headers).json()
    assert [item["id"] for item in listed] == [row["id"]]
    assert "token" not in listed[0] and "token_hash" not in listed[0]


@pytest.mark.unit
def test_community_plan_is_refused(test_client, admin_headers):
    response = test_client.get(f"{BASE}/connections", headers=admin_headers)
    assert response.status_code == 403
    detail = response.json()["detail"]
    assert detail["key"] == "backend.errors.plan.featureNotAvailable"
    assert detail["feature"] == "mcp"


@pytest.mark.unit
def test_config_read_by_anyone_written_by_admins(
    test_client, admin_headers, auth_headers, pro_plan
):
    config = test_client.get(f"{BASE}/config", headers=auth_headers).json()
    assert config == {
        "enabled": True,
        "max_access_level": "full",
        "endpoint_path": "/mcp",
        "available_levels": ["read", "operate", "manage", "full"],
    }
    denied = test_client.put(
        f"{BASE}/config", json={"enabled": False}, headers=auth_headers
    )
    assert denied.status_code == 403
    changed = test_client.put(
        f"{BASE}/config",
        json={"enabled": False, "max_access_level": "operate"},
        headers=admin_headers,
    )
    assert changed.status_code == 200
    assert changed.json()["enabled"] is False
    assert changed.json()["max_access_level"] == "operate"


@pytest.mark.unit
def test_users_only_see_their_own_connections(
    test_client, admin_headers, auth_headers, create_connection
):
    mine, _ = create_connection(auth_headers, name="viewer laptop")
    admins, _ = create_connection(admin_headers, name="admin laptop")
    own = test_client.get(f"{BASE}/connections", headers=auth_headers).json()
    assert [item["id"] for item in own] == [mine["id"]]
    assert (
        test_client.get(
            f"{BASE}/connections?all=true", headers=auth_headers
        ).status_code
        == 403
    )
    every = test_client.get(
        f"{BASE}/connections?all=true", headers=admin_headers
    ).json()
    assert {item["id"] for item in every} == {mine["id"], admins["id"]}
    for method in ("patch", "delete"):
        kwargs = {"json": {"name": "x"}} if method == "patch" else {}
        response = getattr(test_client, method)(
            f"{BASE}/connections/{admins['id']}", headers=auth_headers, **kwargs
        )
        assert response.status_code == 404
    assert (
        test_client.get(
            f"{BASE}/connections/{admins['id']}/activity", headers=auth_headers
        ).status_code
        == 404
    )
    assert (
        test_client.delete(
            f"{BASE}/connections/{mine['id']}", headers=admin_headers
        ).status_code
        == 204
    )


@pytest.mark.unit
def test_level_above_cap_is_refused(test_client, test_db, admin_headers, pro_plan):
    _cap(test_db, "operate")
    response = test_client.post(
        f"{BASE}/connections",
        json={"name": "x", "access_level": "full"},
        headers=admin_headers,
    )
    assert response.status_code == 422
    assert response.json()["detail"]["key"] == "backend.errors.mcp.levelAboveCap"
    assert response.json()["detail"]["params"] == {"max": "operate"}


@pytest.mark.unit
def test_skip_confirmations_needs_full(test_client, admin_headers, pro_plan):
    response = test_client.post(
        f"{BASE}/connections",
        json={
            "name": "x",
            "access_level": "manage",
            "skip_routine_confirmations": True,
        },
        headers=admin_headers,
    )
    assert response.status_code == 422
    assert response.json()["detail"]["key"] == "backend.errors.mcp.skipNeedsFull"


@pytest.mark.unit
def test_lowering_full_drops_the_skip(test_client, admin_headers, pro_plan):
    created = test_client.post(
        f"{BASE}/connections",
        json={"name": "x", "access_level": "full", "skip_routine_confirmations": True},
        headers=admin_headers,
    ).json()
    response = test_client.patch(
        f"{BASE}/connections/{created['id']}",
        json={"access_level": "read"},
        headers=admin_headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["access_level"] == "read"
    assert response.json()["skip_routine_confirmations"] is False


@pytest.mark.unit
def test_blank_name_and_unknown_level_are_refused(test_client, admin_headers, pro_plan):
    blank = test_client.post(
        f"{BASE}/connections",
        json={"name": "  ", "access_level": "read"},
        headers=admin_headers,
    )
    assert blank.json()["detail"]["key"] == "backend.errors.mcp.nameRequired"
    bad = test_client.post(
        f"{BASE}/connections",
        json={"name": "x", "access_level": "root"},
        headers=admin_headers,
    )
    assert bad.status_code == 422


@pytest.mark.unit
def test_lowering_the_cap_keeps_the_chosen_level(
    test_client, test_db, admin_headers, create_connection
):
    row, _ = create_connection(admin_headers, level="full")
    _cap(test_db, "read")
    listed = test_client.get(f"{BASE}/connections", headers=admin_headers).json()[0]
    assert listed["access_level"] == "full"
    assert listed["effective_level"] == "read"


@pytest.mark.unit
def test_patch_changes_level(test_client, admin_headers, create_connection):
    row, _ = create_connection(admin_headers, level="read")
    response = test_client.patch(
        f"{BASE}/connections/{row['id']}",
        json={"access_level": "manage", "name": "renamed"},
        headers=admin_headers,
    )
    assert response.status_code == 200
    assert response.json()["access_level"] == "manage"
    assert response.json()["name"] == "renamed"


@pytest.mark.unit
def test_level_without_tools_is_refused(
    test_client, admin_headers, pro_plan, monkeypatch
):
    monkeypatch.setattr("app.api.mcp_connections.top_level", lambda: Level.READ)
    response = test_client.post(
        f"{BASE}/connections",
        json={"name": "x", "access_level": "operate"},
        headers=admin_headers,
    )
    assert response.status_code == 422
    assert response.json()["detail"] == {
        "key": "backend.errors.mcp.levelNotAvailable",
        "params": {"level": "operate"},
    }


@pytest.mark.unit
def test_config_lists_available_levels(
    test_client, auth_headers, pro_plan, monkeypatch
):
    monkeypatch.setattr("app.api.mcp_connections.top_level", lambda: Level.READ)
    config = test_client.get(f"{BASE}/config", headers=auth_headers).json()
    assert config["available_levels"] == ["read"]


@pytest.mark.unit
def test_rows_count_calls_today(
    test_client, test_db, test_user, auth_headers, create_connection, monkeypatch
):
    row, _ = create_connection(auth_headers)
    other, _ = create_connection(auth_headers, name="other")
    # A fixed day, so a run that crosses midnight cannot flip the count.
    midnight = datetime(2026, 11, 18)
    monkeypatch.setattr("app.api.mcp_connections._utc_midnight", lambda: midnight)
    for connection_id, when in (
        (row["id"], midnight),
        (row["id"], midnight + timedelta(seconds=5)),
        (row["id"], midnight - timedelta(seconds=1)),
        (other["id"], midnight),
    ):
        test_db.add(
            McpActivity(
                connection_id=connection_id,
                connection_name="x",
                user_id=test_user.id,
                tool="t",
                effective_level="read",
                outcome="ok",
                duration_ms=0,
                created_at=when,
            )
        )
    test_db.commit()
    listed = {
        item["id"]: item["calls_today"]
        for item in test_client.get(f"{BASE}/connections", headers=auth_headers).json()
    }
    assert listed == {row["id"]: 2, other["id"]: 1}


@pytest.mark.unit
def test_skip_only_patch_keeps_the_stored_level(
    test_client, admin_headers, create_connection, monkeypatch
):
    row, _ = create_connection(admin_headers, level="full")
    monkeypatch.setattr("app.api.mcp_connections.top_level", lambda: Level.READ)
    response = test_client.patch(
        f"{BASE}/connections/{row['id']}",
        json={"skip_routine_confirmations": True},
        headers=admin_headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["skip_routine_confirmations"] is True


@pytest.mark.unit
def test_beta_off_refuses_create_but_keeps_list_and_revoke(
    test_client, test_db, admin_headers, create_connection, mcp_beta_on
):
    row, _ = create_connection(admin_headers)
    mcp_beta_on.mcp_beta_enabled = False
    test_db.commit()

    response = test_client.post(
        f"{BASE}/connections",
        json={"name": "second", "access_level": "read"},
        headers=admin_headers,
    )
    assert response.status_code == 403
    assert response.json()["detail"]["key"] == "backend.errors.mcp.betaDisabled"

    listed = test_client.get(f"{BASE}/connections", headers=admin_headers).json()
    assert [item["id"] for item in listed] == [row["id"]]
    revoked = test_client.delete(
        f"{BASE}/connections/{row['id']}", headers=admin_headers
    )
    assert revoked.status_code == 204


@pytest.mark.unit
def test_beta_switch_round_trips_through_system_settings(
    test_client, test_db, admin_headers, mcp_beta_on
):
    mcp_beta_on.mcp_beta_enabled = False
    test_db.commit()
    url = "/api/settings/system"
    assert (
        test_client.get(url, headers=admin_headers).json()["settings"][
            "mcp_beta_enabled"
        ]
        is False
    )
    assert (
        test_client.put(
            url, json={"mcp_beta_enabled": True}, headers=admin_headers
        ).status_code
        == 200
    )
    assert (
        test_client.get(url, headers=admin_headers).json()["settings"][
            "mcp_beta_enabled"
        ]
        is True
    )


@pytest.mark.unit
def test_non_admin_cannot_change_the_beta_switch(
    test_client, test_db, auth_headers, mcp_beta_on
):
    response = test_client.put(
        "/api/settings/system", json={"mcp_beta_enabled": False}, headers=auth_headers
    )
    assert response.status_code == 403
    test_db.refresh(mcp_beta_on)
    assert mcp_beta_on.mcp_beta_enabled is True


@pytest.mark.unit
def test_non_admin_reads_the_beta_switch(test_client, auth_headers, mcp_beta_on):
    # The MCP tab is for every user, so they must see the switch to find it.
    response = test_client.get("/api/settings/system", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["settings"]["mcp_beta_enabled"] is True
