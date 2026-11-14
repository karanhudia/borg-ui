"""An MCP token never works on the REST API (spec 5.2 rule 1)."""

import pytest


@pytest.mark.unit
@pytest.mark.parametrize("header", ["Authorization", "X-Borg-Authorization"])
def test_mcp_token_is_refused_by_rest(
    test_client, admin_headers, create_connection, header
):
    _, token = create_connection(admin_headers, level="full")
    response = test_client.get(
        "/api/repositories/", headers={header: f"Bearer {token}"}
    )
    assert response.status_code == 401
    assert response.json()["detail"]["key"] == "backend.errors.auth.mcpTokenNotForApi"


@pytest.mark.unit
def test_personal_tokens_list_hides_mcp_connections(
    test_client, admin_headers, create_connection
):
    row, _ = create_connection(admin_headers)
    listed = test_client.get("/api/settings/tokens", headers=admin_headers).json()
    assert all(item["id"] != row["id"] for item in listed)
    response = test_client.delete(
        f"/api/settings/tokens/{row['id']}", headers=admin_headers
    )
    assert response.status_code == 404


@pytest.mark.unit
def test_personal_token_still_works(test_client, admin_headers):
    created = test_client.post(
        "/api/settings/tokens", json={"name": "ci"}, headers=admin_headers
    ).json()
    response = test_client.get(
        "/api/repositories/", headers={"Authorization": f"Bearer {created['token']}"}
    )
    assert response.status_code == 200
