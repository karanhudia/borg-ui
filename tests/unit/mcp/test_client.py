"""In-process REST client used by MCP tools (plan Task 3)."""

import pytest

from app.mcp.client import ApiError, InternalClient


@pytest.fixture
def client_for(
    test_client, session_per_request, admin_user, create_connection, admin_headers
):
    from app.main import app

    row, _ = create_connection(admin_headers)
    return InternalClient(app, user_id=admin_user.id, connection_id=row["id"])


@pytest.mark.unit
async def test_get_returns_parsed_json(client_for):
    assert (await client_for.get("/api/repositories/"))["repositories"] == []


@pytest.mark.unit
async def test_not_found_raises(client_for):
    with pytest.raises(ApiError) as caught:
        await client_for.get("/api/repositories/987654")
    assert caught.value.status == 404


@pytest.mark.unit
async def test_keyed_errors_carry_key_and_params(client_for, test_db):
    from app.database.models import LicensingState

    test_db.query(LicensingState).update({"plan": "community"})
    test_db.commit()
    with pytest.raises(ApiError) as caught:
        await client_for.get("/api/settings/mcp/config")
    # Refused before the plan check can run: tools never reach MCP settings.
    assert caught.value.status == 403
    assert caught.value.key in (
        "backend.errors.plan.featureNotAvailable",
        "backend.errors.auth.notAvailableOverMcp",
    )


@pytest.mark.unit
async def test_plan_refusal_params(client_for, test_db):
    from app.database.models import LicensingState

    test_db.query(LicensingState).update({"plan": "community"})
    test_db.commit()
    with pytest.raises(ApiError) as caught:
        await client_for.get("/api/rclone/oauth/credentials")
    assert caught.value.key == "backend.errors.plan.featureNotAvailable"
    assert caught.value.params["required"] == "pro"


@pytest.mark.unit
async def test_none_params_are_dropped(client_for):
    assert (await client_for.get("/api/repositories/", unused=None))[
        "repositories"
    ] == []


@pytest.mark.unit
async def test_a_query_parameter_called_path_is_allowed(client_for):
    # The URL argument is positional-only, so tools can send ?path=...
    with pytest.raises(ApiError) as caught:
        await client_for.get("/api/repositories/987654/history", path="home/x")
    assert caught.value.status == 404


@pytest.mark.unit
async def test_a_crashing_route_is_a_500(client_for, monkeypatch):
    def explode(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(
        "app.api.dashboard.accessible_repository_ids", explode, raising=False
    )
    monkeypatch.setattr("app.api.operations.accessible_repository_ids", explode)
    with pytest.raises(ApiError) as caught:
        await client_for.get("/api/dashboard/overview")
    assert caught.value.status == 500
