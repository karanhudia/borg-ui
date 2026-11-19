"""The /mcp endpoint: auth, gating, level filter, transport rules (plan Task 4)."""

import pytest

from app.database.models import ApiToken, SystemSettings, User
from tests.unit.mcp.test_registry import register_pair


@pytest.fixture
def setup(scratch_tools, admin_headers, create_connection, test_db):
    register_pair()

    def make(level="read"):
        row, token = create_connection(
            admin_headers, name=f"{level} laptop", level=level
        )
        return row, token

    return make


def _settings(test_db):
    settings = test_db.query(SystemSettings).first()
    if settings is None:
        settings = SystemSettings()
        test_db.add(settings)
        test_db.commit()
    return settings


@pytest.mark.unit
def test_refuses_missing_and_wrong_tokens(
    test_client, admin_headers, admin_token, setup
):
    personal = test_client.post(
        "/api/settings/tokens", json={"name": "ci"}, headers=admin_headers
    ).json()["token"]
    for headers in (
        {},
        {"Authorization": f"Bearer {personal}"},
        {"Authorization": f"Bearer {admin_token}"},
    ):
        response = test_client.post("/mcp", json={}, headers=headers)
        assert response.status_code == 401
        assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.unit
def test_initialize_names_the_server_and_saves_the_client(mcp, setup, test_db):
    row, token = setup()
    result = mcp(token).initialize(client_name="claude-code", version="2.0.1")
    assert result["serverInfo"]["name"] == "borg-ui"
    assert result["serverInfo"]["title"] == "Borg UI"
    assert "Borg UI" in result["instructions"]
    test_db.expire_all()
    saved = test_db.get(ApiToken, row["id"])
    assert (saved.last_client_name, saved.last_client_version) == (
        "claude-code",
        "2.0.1",
    )


@pytest.mark.unit
def test_list_and_call_follow_the_level(mcp, setup):
    _, token = setup("read")
    session = mcp(token)
    names = {t["name"] for t in session.list_tools()}
    assert "zz_read_echo" in names and "zz_full_echo" not in names
    echo = next(t for t in session.list_tools() if t["name"] == "zz_read_echo")
    assert echo["title"] == "Echo"
    assert echo["annotations"]["readOnlyHint"] is True
    assert echo["annotations"]["openWorldHint"] is False
    assert session.call("zz_read_echo", word="hi")["text"] == "✓ hi"
    refused = session.call("zz_full_echo", word="hi")
    assert refused["is_error"] and "needs full" in refused["text"]


@pytest.mark.unit
def test_admin_cap_lowers_the_level(mcp, setup, test_db):
    _, token = setup("full")
    _settings(test_db).mcp_max_access_level = "read"
    test_db.commit()
    names = {t["name"] for t in mcp(token).list_tools()}
    assert "zz_full_echo" not in names


@pytest.mark.unit
@pytest.mark.parametrize("method", ["get", "delete"])
def test_get_and_delete_answer_405_at_once(test_client, setup, method):
    _, token = setup()
    response = getattr(test_client, method)(
        "/mcp", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 405
    assert response.headers["allow"] == "POST"


@pytest.mark.unit
def test_origin_must_be_this_host(mcp, setup):
    _, token = setup()
    session = mcp(token)
    assert (
        session.post(
            "tools/list", headers={"Origin": "https://evil.example"}
        ).status_code
        == 403
    )
    assert (
        session.post("tools/list", headers={"Origin": "http://testserver"}).status_code
        == 200
    )
    assert session.post("tools/list").status_code == 200


@pytest.mark.unit
def test_community_plan_answers_with_a_friendly_error(mcp, setup, test_db):
    from app.database.models import LicensingState

    _, token = setup()
    test_db.query(LicensingState).update({"plan": "community"})
    test_db.commit()
    result = mcp(token).call("zz_read_echo", word="hi")
    assert result["is_error"] and "Borg UI Pro" in result["text"]


@pytest.mark.unit
def test_admin_switch_answers_with_a_friendly_error(mcp, setup, test_db):
    _, token = setup()
    _settings(test_db).mcp_enabled = False
    test_db.commit()
    result = mcp(token).call("zz_read_echo", word="hi")
    assert result["is_error"] and "administrator" in result["text"]


@pytest.mark.unit
def test_beta_switch_off_refuses_every_call(mcp, setup, test_db):
    _, token = setup()
    _settings(test_db).mcp_beta_enabled = False
    test_db.commit()
    result = mcp(token).call("zz_read_echo", word="hi")
    assert result["is_error"] and "Settings > Advanced > Beta" in result["text"]


@pytest.mark.unit
def test_revoked_connection_is_refused_next_call(
    test_client, mcp, setup, admin_headers
):
    row, token = setup()
    session = mcp(token)
    assert session.call("zz_read_echo", word="hi")["text"] == "✓ hi"
    test_client.delete(
        f"/api/settings/mcp/connections/{row['id']}", headers=admin_headers
    )
    assert session.post("tools/list").status_code == 401


@pytest.mark.unit
def test_deactivated_user_is_refused_next_call(mcp, setup, test_db, admin_user):
    _, token = setup()
    session = mcp(token)
    assert session.call("zz_read_echo", word="hi")["text"] == "✓ hi"
    test_db.query(User).filter(User.id == admin_user.id).update({"is_active": False})
    test_db.commit()
    assert session.post("tools/list").status_code == 401


@pytest.mark.unit
def test_bad_arguments_name_the_field_not_the_value(mcp, setup):
    _, token = setup()
    result = mcp(token).call("zz_read_echo", word=["secret-value-123"])
    assert result["is_error"]
    assert "word" in result["text"]
    assert "secret-value-123" not in result["text"]


@pytest.mark.unit
def test_spa_paths_still_serve_the_app(test_client):
    response = test_client.get("/mcp-settings")
    assert response.status_code == 200
    assert "html" in response.headers["content-type"]


@pytest.mark.unit
def test_works_below_a_base_path(test_client, setup):
    from fastapi.testclient import TestClient

    from app.main import BasePathMiddleware, app
    from tests.unit.mcp.conftest import McpSession

    _, token = setup()
    wrapped = TestClient(BasePathMiddleware(app, base_path="/borg"))
    for path in ("/borg/mcp", "/mcp"):  # direct, and behind a prefix-stripping proxy
        session = McpSession(wrapped, token, path)
        assert session.call("zz_read_echo", word="hi")["text"] == "✓ hi"


@pytest.mark.unit
def test_oversized_body_is_refused_before_buffering(test_client, setup):
    _, token = setup()
    response = test_client.post(
        "/mcp",
        content=b"x" * (4 * 1024 * 1024 + 1),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    assert response.status_code == 413


@pytest.mark.unit
async def test_read_body_stops_at_the_limit():
    from app.mcp.server import MAX_BODY, _read_body

    reads = 0

    async def endless():
        nonlocal reads
        reads += 1
        return {"body": b"x" * 65536, "more_body": True}

    assert await _read_body(endless) is None
    assert reads <= MAX_BODY // 65536 + 1


@pytest.mark.unit
def test_answers_are_event_streams(admin_mcp):
    """Progress rides on the call's own answer, which JSON mode cannot carry
    (spec 5.8), so requests are answered as an event stream."""
    response = admin_mcp.post("tools/list")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert admin_mcp.result(response)["tools"]
