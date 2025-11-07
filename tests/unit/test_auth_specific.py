"""
Specific, meaningful tests for authentication.
Tests the fixes for inactive user returning 401 instead of 400.
"""
import pytest
from fastapi.testclient import TestClient
from app.database.models import User
from app.core.security import get_password_hash


@pytest.mark.unit
class TestAuthenticationStatusCodes:
    """Test that authentication returns correct HTTP status codes"""

    def test_login_with_wrong_password_returns_401(
        self,
        test_client: TestClient,
        test_db
    ):
        """Should return 401 for incorrect password"""
        # Create a user
        user = User(
            username="testuser",
            password_hash=get_password_hash("correctpassword"),
            is_active=True,
            is_admin=False
        )
        test_db.add(user)
        test_db.commit()

        # Try to login with wrong password
        response = test_client.post(
            "/api/auth/login",
            data={
                "username": "testuser",
                "password": "wrongpassword"
            }
        )

        assert response.status_code == 401
        assert "Incorrect username or password" in response.json()["detail"]

    def test_login_with_nonexistent_user_returns_401(self, test_client: TestClient):
        """Should return 401 for non-existent user"""
        response = test_client.post(
            "/api/auth/login",
            data={
                "username": "nonexistent",
                "password": "password"
            }
        )

        assert response.status_code == 401
        assert "Incorrect username or password" in response.json()["detail"]

    def test_login_with_inactive_user_returns_401(
        self,
        test_client: TestClient,
        test_db
    ):
        """
        CRITICAL TEST: Inactive user should return 401, NOT 400.
        This tests the fix for the bug where inactive users got HTTP_400_BAD_REQUEST.
        """
        # Create an inactive user
        user = User(
            username="inactive_user",
            password_hash=get_password_hash("password123"),
            is_active=False,
            is_admin=False
        )
        test_db.add(user)
        test_db.commit()

        # Try to login with inactive user
        response = test_client.post(
            "/api/auth/login",
            data={
                "username": "inactive_user",
                "password": "password123"
            }
        )

        # MUST be 401 (authentication failure), NOT 400 (validation error)
        assert response.status_code == 401, \
            f"Expected 401 for inactive user, got {response.status_code}. " \
            f"This means the inactive user bug fix was not applied!"
        assert "Inactive user" in response.json()["detail"]

    def test_access_protected_endpoint_with_invalid_token_returns_401(
        self,
        test_client: TestClient
    ):
        """Should return 401 for invalid JWT token"""
        response = test_client.get(
            "/api/repositories/",
            headers={"Authorization": "Bearer invalid_token_here"}
        )

        assert response.status_code == 401

    def test_access_protected_endpoint_without_token_returns_403(
        self,
        test_client: TestClient
    ):
        """
        Currently returns 403 when no token is provided.
        NOTE: FastAPI's HTTPBearer returns 403 for missing credentials.
        """
        response = test_client.get("/api/repositories/")

        assert response.status_code == 403


@pytest.mark.unit
class TestAuthenticationSuccessCases:
    """Test successful authentication scenarios"""

    def test_login_with_correct_credentials_returns_200(
        self,
        test_client: TestClient,
        test_db
    ):
        """Should return 200 and access token for valid credentials"""
        # Create an active user
        user = User(
            username="activeuser",
            password_hash=get_password_hash("password123"),
            is_active=True,
            is_admin=False
        )
        test_db.add(user)
        test_db.commit()

        # Login with correct credentials
        response = test_client.post(
            "/api/auth/login",
            data={
                "username": "activeuser",
                "password": "password123"
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

    def test_access_protected_endpoint_with_valid_token_succeeds(
        self,
        test_client: TestClient,
        admin_headers
    ):
        """Should allow access to protected endpoint with valid token"""
        response = test_client.get(
            "/api/repositories/",
            headers=admin_headers
        )

        # Should succeed (not test exact code since it depends on data)
        assert response.status_code in [200, 204]


@pytest.mark.unit
class TestTokenValidation:
    """Test JWT token validation in protected endpoints"""

    def test_expired_token_returns_401(self, test_client: TestClient):
        """Should return 401 for expired token"""
        # Use a token that's clearly expired (past timestamp)
        expired_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJhZG1pbiIsImV4cCI6MTUxNjIzOTAyMn0.4Adcj0vVzR3aP_-3dFvmn3o9F3xqCKuXqCxBZu9cZqw"

        response = test_client.get(
            "/api/repositories/",
            headers={"Authorization": f"Bearer {expired_token}"}
        )

        assert response.status_code == 401

    def test_malformed_token_returns_401(self, test_client: TestClient):
        """Should return 401 for malformed token"""
        response = test_client.get(
            "/api/repositories/",
            headers={"Authorization": "Bearer not.a.valid.jwt"}
        )

        assert response.status_code == 401

    def test_missing_bearer_prefix_returns_403(self, test_client: TestClient):
        """
        Currently returns 403 when token doesn't have Bearer prefix.
        FastAPI's HTTPBearer validates the authorization scheme.
        """
        response = test_client.get(
            "/api/repositories/",
            headers={"Authorization": "InvalidPrefix token_here"}
        )

        assert response.status_code == 403
