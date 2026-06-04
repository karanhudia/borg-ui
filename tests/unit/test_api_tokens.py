# tests/unit/test_api_tokens.py
"""
Unit tests for API token endpoints.
"""

import pytest
from fastapi.testclient import TestClient
from app.database.models import User


@pytest.mark.unit
class TestApiTokens:
    def test_list_tokens_empty(self, test_client: TestClient, admin_headers):
        """New user has no tokens"""
        response = test_client.get("/api/settings/tokens", headers=admin_headers)
        assert response.status_code == 200
        assert response.json() == []

    def test_generate_token_returns_full_token_once(
        self, test_client: TestClient, admin_headers
    ):
        """Generated token is returned in full only at creation time"""
        response = test_client.post(
            "/api/settings/tokens",
            json={"name": "My CI token"},
            headers=admin_headers,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "My CI token"
        assert data["token"].startswith("borgui_")
        assert len(data["token"]) > 20
        assert data["prefix"] == data["token"][:12]
        assert data["created_at"].endswith("+00:00")

    def test_list_tokens_after_generate_shows_prefix_not_token(
        self, test_client: TestClient, admin_headers
    ):
        """Token list shows prefix, never the full token"""
        test_client.post(
            "/api/settings/tokens", json={"name": "tok"}, headers=admin_headers
        )
        response = test_client.get("/api/settings/tokens", headers=admin_headers)
        assert response.status_code == 200
        tokens = response.json()
        assert len(tokens) == 1
        assert "token" not in tokens[0]
        assert tokens[0]["prefix"].startswith("borgui_")
        assert tokens[0]["created_at"].endswith("+00:00")

    def test_generate_token_empty_name_returns_422(
        self, test_client: TestClient, admin_headers
    ):
        """Empty token name is rejected"""
        response = test_client.post(
            "/api/settings/tokens",
            json={"name": "   "},
            headers=admin_headers,
        )
        assert response.status_code == 422

    def test_revoke_token(self, test_client: TestClient, admin_headers):
        """Revoking a token removes it from list"""
        create = test_client.post(
            "/api/settings/tokens",
            json={"name": "to revoke"},
            headers=admin_headers,
        )
        token_id = create.json()["id"]

        revoke = test_client.delete(
            f"/api/settings/tokens/{token_id}", headers=admin_headers
        )
        assert revoke.status_code == 204

        list_resp = test_client.get("/api/settings/tokens", headers=admin_headers)
        assert list_resp.json() == []

    def test_revoke_nonexistent_token_returns_404(
        self, test_client: TestClient, admin_headers
    ):
        """Revoking a token that does not exist returns 404"""
        response = test_client.delete(
            "/api/settings/tokens/99999", headers=admin_headers
        )
        assert response.status_code == 404

    def test_revoke_other_users_token_returns_403(
        self, test_client: TestClient, test_db, admin_headers
    ):
        """Non-admin cannot revoke another user's token"""
        from app.core.security import get_password_hash, create_access_token

        other = User(
            username="other",
            password_hash=get_password_hash("pass"),
            is_active=True,
            role="viewer",
        )
        test_db.add(other)
        test_db.commit()
        test_db.refresh(other)

        other_token = create_access_token(data={"sub": other.username})
        other_headers = {"Authorization": f"Bearer {other_token}"}

        # admin creates a token
        create = test_client.post(
            "/api/settings/tokens", json={"name": "admin tok"}, headers=admin_headers
        )
        token_id = create.json()["id"]

        # other user tries to revoke it
        response = test_client.delete(
            f"/api/settings/tokens/{token_id}", headers=other_headers
        )
        assert response.status_code == 403

    def test_unauthenticated_returns_401(self, test_client: TestClient):
        """Token endpoints require authentication"""
        assert test_client.get("/api/settings/tokens").status_code == 401
