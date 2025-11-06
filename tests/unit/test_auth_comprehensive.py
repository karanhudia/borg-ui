"""
Comprehensive authentication and authorization tests
"""
import pytest
from fastapi.testclient import TestClient
from app.database.models import User
from app.core.security import get_password_hash, verify_password, create_access_token


@pytest.mark.unit
class TestPasswordSecurity:
    """Test password hashing and verification"""

    def test_password_hashing_consistent(self):
        """Test that password hashing is consistent"""
        password = "test_password_123"
        hash1 = get_password_hash(password)

        assert hash1 is not None
        assert isinstance(hash1, str)
        assert len(hash1) > 0
        assert hash1 != password  # Hash should be different from password

    def test_password_verification_valid(self):
        """Test password verification with correct password"""
        password = "test_password_123"
        password_hash = get_password_hash(password)

        assert verify_password(password, password_hash) is True

    def test_password_verification_invalid(self):
        """Test password verification with wrong password"""
        password = "test_password_123"
        wrong_password = "wrong_password"
        password_hash = get_password_hash(password)

        assert verify_password(wrong_password, password_hash) is False

    def test_password_hash_different_each_time(self):
        """Test that same password produces different hashes (salt)"""
        password = "test_password_123"
        hash1 = get_password_hash(password)
        hash2 = get_password_hash(password)

        # Hashes should be different due to salt
        assert hash1 != hash2
        # But both should verify correctly
        assert verify_password(password, hash1)
        assert verify_password(password, hash2)


@pytest.mark.unit
class TestTokenGeneration:
    """Test JWT token generation"""

    def test_create_access_token_basic(self):
        """Test creating basic access token"""
        token = create_access_token(data={"sub": "testuser"})

        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 0
        # JWT tokens have three parts separated by dots
        assert token.count('.') == 2

    def test_create_access_token_with_extra_data(self):
        """Test creating token with additional claims"""
        token = create_access_token(
            data={
                "sub": "testuser",
                "role": "admin",
                "permissions": ["read", "write"]
            }
        )

        assert token is not None
        assert isinstance(token, str)

    def test_tokens_are_different(self):
        """Test that different users get different tokens"""
        token1 = create_access_token(data={"sub": "user1"})
        token2 = create_access_token(data={"sub": "user2"})

        assert token1 != token2


@pytest.mark.unit
class TestUserManagement:
    """Test user management operations"""

    def test_create_user_in_database(self, db_session):
        """Test creating user in database"""
        user = User(
            username="newuser",
            password_hash=get_password_hash("password123"),
            is_active=True
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)

        assert user.id is not None
        assert user.username == "newuser"
        assert user.is_active is True

    def test_find_user_by_username(self, db_session):
        """Test finding user by username"""
        user = User(
            username="findme",
            password_hash=get_password_hash("password123"),
            is_active=True
        )
        db_session.add(user)
        db_session.commit()

        found_user = db_session.query(User).filter(User.username == "findme").first()

        assert found_user is not None
        assert found_user.username == "findme"

    def test_user_unique_username_constraint(self, db_session):
        """Test that username must be unique"""
        user1 = User(
            username="duplicate",
            password_hash=get_password_hash("password123"),
            is_active=True
        )
        db_session.add(user1)
        db_session.commit()

        user2 = User(
            username="duplicate",
            password_hash=get_password_hash("password456"),
            is_active=True
        )
        db_session.add(user2)

        with pytest.raises(Exception):  # Should raise integrity error
            db_session.commit()

    def test_deactivate_user(self, db_session):
        """Test deactivating user account"""
        user = User(
            username="deactivate_me",
            password_hash=get_password_hash("password123"),
            is_active=True
        )
        db_session.add(user)
        db_session.commit()

        user.is_active = False
        db_session.commit()

        assert user.is_active is False


@pytest.mark.unit
class TestAuthenticationEndpoints:
    """Test authentication endpoint behavior"""

    def test_login_with_form_data(self, test_client: TestClient, test_user):
        """Test login endpoint with form data"""
        response = test_client.post(
            "/api/auth/login",
            data={
                "username": "testuser",
                "password": "testpass123"
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "token_type" in data
        assert data["token_type"] == "bearer"

    def test_login_case_sensitive_username(self, test_client: TestClient, test_user):
        """Test that username is case sensitive"""
        response = test_client.post(
            "/api/auth/login",
            data={
                "username": "TESTUSER",  # Wrong case
                "password": "testpass123"
            }
        )

        # Should fail with case mismatch
        assert response.status_code == 401

    def test_login_empty_credentials(self, test_client: TestClient):
        """Test login with empty credentials"""
        response = test_client.post(
            "/api/auth/login",
            data={
                "username": "",
                "password": ""
            }
        )

        assert response.status_code in [401, 422]

    def test_login_sql_injection_attempt(self, test_client: TestClient):
        """Test that SQL injection is prevented"""
        response = test_client.post(
            "/api/auth/login",
            data={
                "username": "admin' OR '1'='1",
                "password": "anything"
            }
        )

        assert response.status_code == 401

    def test_protected_endpoint_without_token(self, test_client: TestClient):
        """Test accessing protected endpoint without token"""
        response = test_client.get("/api/auth/me")

        assert response.status_code in [401, 403]

    def test_protected_endpoint_with_malformed_token(self, test_client: TestClient):
        """Test accessing protected endpoint with malformed token"""
        response = test_client.get(
            "/api/auth/me",
            headers={"Authorization": "Bearer malformed_token"}
        )

        assert response.status_code in [401, 403]

    def test_protected_endpoint_with_expired_token(self, test_client: TestClient):
        """Test accessing protected endpoint with expired token"""
        # Create a token with negative expiry (already expired)
        from datetime import timedelta
        expired_token = create_access_token(
            data={"sub": "testuser"},
            expires_delta=timedelta(minutes=-10)
        )

        response = test_client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {expired_token}"}
        )

        assert response.status_code in [401, 403]

    def test_protected_endpoint_missing_bearer_prefix(self, test_client: TestClient, auth_token):
        """Test accessing protected endpoint without Bearer prefix"""
        response = test_client.get(
            "/api/auth/me",
            headers={"Authorization": auth_token}  # Missing "Bearer" prefix
        )

        assert response.status_code in [401, 403]
