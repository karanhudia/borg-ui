"""Manage: settings and users (plan phase 4, Task 8; spec 5.2 rule 5, 5.9)."""

import pytest
from pydantic import ValidationError

from app.mcp.client import ApiError
from app.mcp.registry import REGISTRY
from tests.unit.mcp.test_tools_stubbed import run

SETTINGS = {
    "/api/settings/system": {
        "success": True,
        "settings": {"stats_refresh_interval_minutes": 60, "log_retention_days": 30},
    }
}


@pytest.mark.unit
@pytest.mark.parametrize(
    "field",
    [
        "mcp_beta_enabled",
        "metrics_token",
        "rotate_metrics_token",
        "metrics_enabled",
        "mqtt_password",
        "mqtt_tls_client_key",
        "webhook_url",
        "email_notifications",
        "lock_breaking_enabled",
    ],
)
def test_update_settings_refuses_kept_out_fields(field):
    with pytest.raises(ValidationError):
        REGISTRY["update_settings"].input_model(**{field: True})


@pytest.mark.unit
def test_allowlist_is_a_subset_of_the_route_model():
    from app.api.settings import SystemSettingsUpdate
    from app.mcp.tools.manage_settings import UPDATE_SETTINGS_FIELDS

    assert UPDATE_SETTINGS_FIELDS <= set(SystemSettingsUpdate.model_fields)
    assert not any(
        f.startswith(("mcp", "metrics", "mqtt")) for f in UPDATE_SETTINGS_FIELDS
    )


@pytest.mark.unit
def test_update_settings_sends_only_changes():
    routes = {**SETTINGS, "PUT /api/settings/system": {"success": True}}
    result, api = run("update_settings", routes, stats_refresh_interval_minutes=15)
    assert api.puts == [
        ("/api/settings/system", {"stats_refresh_interval_minutes": 15})
    ]
    assert "60 → 15" in result.text


@pytest.mark.unit
def test_update_settings_nothing_to_change():
    result, api = run("update_settings", dict(SETTINGS))
    assert api.puts == []
    assert result.is_error


USERS = {
    "/api/settings/users": {
        "users": [
            {"id": 1, "username": "admin", "role": "admin", "is_active": True},
            {"id": 2, "username": "sam", "role": "viewer", "is_active": True},
        ]
    }
}


@pytest.mark.unit
def test_update_user_changes_role():
    routes = {**USERS, "PUT /api/settings/users/2": {"success": True}}
    result, api = run("update_user", routes, user="sam", role="operator")
    assert api.puts == [("/api/settings/users/2", {"role": "operator"})]
    assert "viewer → operator" in result.text


@pytest.mark.unit
def test_update_user_refuses_self():
    # run() connects as user id 1 ("admin")
    result, api = run("update_user", dict(USERS), user="admin", role="viewer")
    assert api.puts == []
    assert result.is_error
    assert "web UI" in result.text


@pytest.mark.unit
@pytest.mark.parametrize(
    "field", ["username", "auth_source", "oidc_subject", "password"]
)
def test_update_user_rejects_kept_out_fields(field):
    with pytest.raises(ValidationError):
        REGISTRY["update_user"].input_model(user="sam", **{field: "x"})


@pytest.mark.unit
def test_update_user_refuses_non_admin():
    routes = {
        "/api/settings/users": ApiError(
            403, "backend.errors.settings.adminAccessRequired"
        )
    }

    class Raising(dict):
        def __getitem__(self, key):
            value = dict.__getitem__(self, key)
            if isinstance(value, Exception):
                raise value
            return value

    with pytest.raises(ApiError):
        run("update_user", Raising(routes), user="sam", role="admin")


@pytest.mark.unit
def test_create_user_hands_off_without_posting():
    result, api = run(
        "create_user",
        dict(USERS),
        username="robin",
        email="robin@example.invalid",
        role="operator",
    )
    assert api.posts == []
    assert "/settings/users?new=1&username=robin" in result.text
    assert "role=operator" in result.text
    assert "password" not in result.text.split("?", 1)[1].split()[0]
    assert "Set their password there" in result.text


@pytest.mark.unit
def test_create_user_taken_name():
    result, api = run("create_user", dict(USERS), username="Sam")
    assert result.is_error
    assert "already" in result.text
