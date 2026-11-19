"""The credential MCP tools use to call the app in-process (plan Task 3)."""

from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.config import settings
from app.core.security import MCP_INTERNAL_HEADER, create_mcp_internal_token
from app.database.models import ApiToken, User

PROFILE = "/api/settings/profile"


def _get(client, credential, path=PROFILE):
    return client.get(path, headers={MCP_INTERNAL_HEADER: credential})


@pytest.fixture
def viewer_connection(test_db, test_user, create_connection, auth_headers):
    row, _ = create_connection(auth_headers)
    return test_user, row["id"]


@pytest.mark.unit
def test_answers_as_the_connections_user(test_client, viewer_connection):
    user, connection_id = viewer_connection
    response = _get(test_client, create_mcp_internal_token(user.id, connection_id))
    assert response.status_code == 200
    assert response.json()["profile"]["username"] == user.username


@pytest.mark.unit
def test_works_in_proxy_auth_mode(test_client, viewer_connection, monkeypatch):
    user, connection_id = viewer_connection
    monkeypatch.setattr("app.core.security.settings.disable_authentication", True)
    response = _get(test_client, create_mcp_internal_token(user.id, connection_id))
    assert response.status_code == 200
    assert response.json()["profile"]["username"] == user.username


@pytest.mark.unit
def test_insecure_no_auth_still_answers_as_the_viewer(
    test_client, viewer_connection, admin_user, monkeypatch
):
    user, connection_id = viewer_connection
    monkeypatch.setattr("app.core.security.settings.allow_insecure_no_auth", True)
    response = _get(test_client, create_mcp_internal_token(user.id, connection_id))
    assert response.json()["profile"]["username"] == user.username


def _forged(user_id, connection_id, **overrides):
    claims = {
        "sub": str(user_id),
        "conn": connection_id,
        "purpose": "mcp_internal",
        "exp": datetime.now(timezone.utc) + timedelta(seconds=60),
        **overrides,
    }
    return jwt.encode(claims, settings.secret_key, algorithm=settings.algorithm)


@pytest.mark.unit
def test_refuses_bad_credentials(test_client, test_db, viewer_connection):
    user, connection_id = viewer_connection
    expired = _forged(
        user.id, connection_id, exp=datetime.now(timezone.utc) - timedelta(seconds=1)
    )
    wrong_signature = jwt.encode(
        {"sub": str(user.id), "conn": connection_id, "purpose": "mcp_internal"},
        "not-the-secret-key-not-the-secret-key",
        algorithm=settings.algorithm,
    )
    access_purpose = _forged(user.id, connection_id, purpose="access")
    for credential in (expired, wrong_signature, access_purpose, "garbage"):
        assert _get(test_client, credential).status_code == 401


@pytest.mark.unit
def test_refuses_once_connection_is_revoked(test_client, test_db, viewer_connection):
    user, connection_id = viewer_connection
    credential = create_mcp_internal_token(user.id, connection_id)
    test_db.query(ApiToken).filter(ApiToken.id == connection_id).delete()
    test_db.commit()
    assert _get(test_client, credential).status_code == 401


@pytest.mark.unit
def test_refuses_a_deactivated_user(test_client, test_db, viewer_connection):
    user, connection_id = viewer_connection
    credential = create_mcp_internal_token(user.id, connection_id)
    test_db.query(User).filter(User.id == user.id).update({"is_active": False})
    test_db.commit()
    assert _get(test_client, credential).status_code == 401


@pytest.mark.unit
def test_refuses_a_connection_of_another_user(
    test_client, admin_user, viewer_connection
):
    _, connection_id = viewer_connection
    assert (
        _get(
            test_client, create_mcp_internal_token(admin_user.id, connection_id)
        ).status_code
        == 401
    )


@pytest.mark.unit
def test_is_not_a_bearer_token(test_client, viewer_connection):
    user, connection_id = viewer_connection
    credential = create_mcp_internal_token(user.id, connection_id)
    response = test_client.get(
        PROFILE, headers={"Authorization": f"Bearer {credential}"}
    )
    assert response.status_code == 401


@pytest.mark.unit
@pytest.mark.parametrize(
    "path", ["/api/settings/tokens", "/api/settings/mcp/connections"]
)
def test_cannot_reach_token_or_mcp_settings(test_client, viewer_connection, path):
    user, connection_id = viewer_connection
    response = _get(
        test_client, create_mcp_internal_token(user.id, connection_id), path
    )
    assert response.status_code == 403
    assert response.json()["detail"]["key"] == "backend.errors.auth.notAvailableOverMcp"
