"""
Comprehensive unit tests for authentication API endpoints and security
Consolidated from test_api_auth.py, test_auth_comprehensive.py, and test_auth_specific.py
"""

from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
import json
import pytest
from fastapi.testclient import TestClient
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from app.database.models import (
    AuthRateLimitBucket,
    OidcExchangeGrant,
    OidcLoginState,
    PasskeyCredential,
    SystemSettings,
    User,
)
from app.core.passkeys import create_passkey_ceremony_token
from app.core.security import (
    create_access_token,
    encrypt_secret,
    get_password_hash,
    verify_password,
)
from app.core.totp import _hotp


def create_test_oidc_exchange_grant(
    db_session,
    *,
    grant_id: str = "grant-123",
    username: str = "oidc-user",
    oidc_subject: str | None = "subject-123",
    email: str | None = "oidc-user@example.com",
    full_name: str | None = "OIDC User",
    groups: list[str] | None = None,
    role: str | None = None,
    all_repositories_role: str | None = None,
    id_token_hint: str | None = "id-token-value",
):
    grant = OidcExchangeGrant(
        grant_id=grant_id,
        username=username,
        oidc_subject=oidc_subject,
        email=email,
        full_name=full_name,
        groups_json=json.dumps(groups or []),
        role=role,
        all_repositories_role=all_repositories_role,
        id_token_hint_encrypted=encrypt_secret(id_token_hint)
        if id_token_hint
        else None,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )
    db_session.add(grant)
    db_session.commit()
    db_session.refresh(grant)
    return grant


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
        assert token.count(".") == 2

    def test_create_access_token_with_extra_data(self):
        """Test creating token with additional claims"""
        token = create_access_token(
            data={"sub": "testuser", "role": "admin", "permissions": ["read", "write"]}
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
            is_active=True,
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
            is_active=True,
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
            is_active=True,
        )
        db_session.add(user1)
        db_session.commit()

        user2 = User(
            username="duplicate",
            password_hash=get_password_hash("password456"),
            is_active=True,
        )
        db_session.add(user2)

        with pytest.raises(Exception):  # Should raise integrity error
            db_session.commit()

    def test_deactivate_user(self, db_session):
        """Test deactivating user account"""
        user = User(
            username="deactivate_me",
            password_hash=get_password_hash("password123"),
            is_active=True,
        )
        db_session.add(user)
        db_session.commit()

        user.is_active = False
        db_session.commit()

        assert user.is_active is False


@pytest.mark.unit
class TestAuthenticationLogin:
    """Test login endpoint behavior"""

    def test_login_success(self, test_client: TestClient, admin_user):
        """Test successful login with admin user"""
        response = test_client.post(
            "/api/auth/login", data={"username": "admin", "password": "admin123"}
        )

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

    def test_login_with_form_data(self, test_client: TestClient, test_user):
        """Test login endpoint with form data"""
        response = test_client.post(
            "/api/auth/login", data={"username": "testuser", "password": "testpass123"}
        )

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "token_type" in data
        assert data["token_type"] == "bearer"

    def test_login_with_correct_credentials_returns_200(
        self, test_client: TestClient, test_db
    ):
        """Should return 200 and access token for valid credentials"""
        # Create an active user
        user = User(
            username="activeuser",
            password_hash=get_password_hash("password123"),
            is_active=True,
            role="viewer",
        )
        test_db.add(user)
        test_db.commit()

        # Login with correct credentials
        response = test_client.post(
            "/api/auth/login",
            data={"username": "activeuser", "password": "password123"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

    def test_login_rate_limits_repeated_failed_attempts(self, test_client: TestClient):
        for _ in range(4):
            response = test_client.post(
                "/api/auth/login",
                data={"username": "admin", "password": "wrong-password"},
            )
            assert response.status_code == 401

        limited_response = test_client.post(
            "/api/auth/login",
            data={"username": "admin", "password": "wrong-password"},
        )

        assert limited_response.status_code == 429
        assert (
            limited_response.json()["detail"]["key"]
            == "backend.errors.auth.tooManyRequests"
        )
        assert "Retry-After" in limited_response.headers

        blocked_success = test_client.post(
            "/api/auth/login",
            data={"username": "admin", "password": "admin123"},
        )
        assert blocked_success.status_code == 429

    def test_login_success_clears_stale_oidc_logout_hint(
        self, test_client: TestClient, test_db
    ):
        user = User(
            username="local-hint-user",
            password_hash=get_password_hash("password123"),
            email="local-hint@example.com",
            role="viewer",
            is_active=True,
            auth_source="oidc",
            oidc_last_id_token_encrypted=encrypt_secret("stale-oidc-id-token"),
        )
        test_db.add(user)
        test_db.commit()

        response = test_client.post(
            "/api/auth/login",
            data={"username": "local-hint-user", "password": "password123"},
        )

        assert response.status_code == 200
        test_db.refresh(user)
        assert user.auth_source == "local"
        assert user.oidc_last_id_token_encrypted is None

    def test_login_invalid_credentials(self, test_client: TestClient, admin_user):
        """Test login with invalid password"""
        response = test_client.post(
            "/api/auth/login", data={"username": "admin", "password": "wrongpassword"}
        )

        assert response.status_code == 401

    def test_login_with_wrong_password_returns_401(
        self, test_client: TestClient, test_db
    ):
        """Should return 401 for incorrect password"""
        # Create a user
        user = User(
            username="testuser",
            password_hash=get_password_hash("correctpassword"),
            is_active=True,
            role="viewer",
        )
        test_db.add(user)
        test_db.commit()

        # Try to login with wrong password
        response = test_client.post(
            "/api/auth/login",
            data={"username": "testuser", "password": "wrongpassword"},
        )

        assert response.status_code == 401
        assert (
            response.json()["detail"]["key"]
            == "backend.errors.auth.incorrectCredentials"
        )

    def test_login_nonexistent_user(self, test_client: TestClient):
        """Test login with non-existent user"""
        response = test_client.post(
            "/api/auth/login", data={"username": "nonexistent", "password": "password"}
        )

        assert response.status_code == 401

    def test_login_with_nonexistent_user_returns_401(self, test_client: TestClient):
        """Should return 401 for non-existent user"""
        response = test_client.post(
            "/api/auth/login", data={"username": "nonexistent", "password": "password"}
        )

        assert response.status_code == 401
        assert (
            response.json()["detail"]["key"]
            == "backend.errors.auth.incorrectCredentials"
        )

    def test_login_with_inactive_user_returns_401(
        self, test_client: TestClient, test_db
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
            role="viewer",
        )
        test_db.add(user)
        test_db.commit()

        # Try to login with inactive user
        response = test_client.post(
            "/api/auth/login",
            data={"username": "inactive_user", "password": "password123"},
        )

        # MUST be 401 (authentication failure), NOT 400 (validation error)
        assert response.status_code == 401, (
            f"Expected 401 for inactive user, got {response.status_code}. "
            f"This means the inactive user bug fix was not applied!"
        )
        assert response.json()["detail"]["key"] == "backend.errors.auth.inactiveUser"

    def test_login_case_sensitive_username(self, test_client: TestClient, test_user):
        """Test that username is case sensitive"""
        response = test_client.post(
            "/api/auth/login",
            data={
                "username": "TESTUSER",  # Wrong case
                "password": "testpass123",
            },
        )

        # Should fail with case mismatch
        assert response.status_code == 401

    def test_login_empty_credentials(self, test_client: TestClient):
        """Test login with empty credentials"""
        response = test_client.post(
            "/api/auth/login", data={"username": "", "password": ""}
        )

        assert response.status_code == 422

    def test_login_sql_injection_attempt(self, test_client: TestClient):
        """Test that SQL injection is prevented"""
        response = test_client.post(
            "/api/auth/login",
            data={"username": "admin' OR '1'='1", "password": "anything"},
        )

        assert response.status_code == 401

    def test_login_with_special_characters_in_password(
        self, test_client: TestClient, test_db
    ):
        """
        Test login with special characters in password (especially '&' which can be problematic in URL encoding).
        This tests the fix for issue #117 where '&' in password prevents login.
        """
        # Create a user with a password containing special characters
        special_password = "test&pass=123%special"
        user = User(
            username="specialuser",
            password_hash=get_password_hash(special_password),
            is_active=True,
            role="viewer",
        )
        test_db.add(user)
        test_db.commit()

        # Login with the special character password
        response = test_client.post(
            "/api/auth/login",
            data={"username": "specialuser", "password": special_password},
        )

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

    def test_login_with_ampersand_in_password(self, test_client: TestClient, test_db):
        """
        Test login with ampersand specifically in password.
        This is a regression test for issue #117.
        """
        # Create a user with an ampersand in the password
        password_with_ampersand = "myPass&word123"
        user = User(
            username="ampersanduser",
            password_hash=get_password_hash(password_with_ampersand),
            is_active=True,
            role="viewer",
        )
        test_db.add(user)
        test_db.commit()

        # Login should succeed
        response = test_client.post(
            "/api/auth/login",
            data={"username": "ampersanduser", "password": password_with_ampersand},
        )

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"


@pytest.mark.unit
class TestProtectedEndpoints:
    """Test protected endpoint access and token validation"""

    def test_get_current_user(self, test_client: TestClient, auth_headers, test_user):
        """Test getting current user info"""
        response = test_client.get("/api/auth/me", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["username"] == test_user.username

    def test_get_current_user_unauthorized(self, test_client: TestClient):
        """Test getting current user without authentication"""
        response = test_client.get("/api/auth/me")

        assert response.status_code == 401

    def test_get_current_user_invalid_token(self, test_client: TestClient):
        """Test getting current user with invalid token"""
        response = test_client.get(
            "/api/auth/me", headers={"X-Borg-Authorization": "Bearer invalid_token"}
        )

        assert response.status_code == 401

    def test_protected_endpoint_without_token(self, test_client: TestClient):
        """Test accessing protected endpoint without token"""
        response = test_client.get("/api/auth/me")

        assert response.status_code == 401

    def test_access_protected_endpoint_without_token_returns_403(
        self, test_client: TestClient
    ):
        """
        Currently returns 403 when no token is provided.
        NOTE: FastAPI's HTTPBearer returns 403 for missing credentials.
        """
        response = test_client.get("/api/repositories/")

        assert response.status_code == 401

    def test_protected_endpoint_with_malformed_token(self, test_client: TestClient):
        """Test accessing protected endpoint with malformed token"""
        response = test_client.get(
            "/api/auth/me", headers={"X-Borg-Authorization": "Bearer malformed_token"}
        )

        assert response.status_code == 401

    def test_access_protected_endpoint_with_invalid_token_returns_401(
        self, test_client: TestClient
    ):
        """Should return 401 for invalid JWT token"""
        response = test_client.get(
            "/api/repositories/",
            headers={"X-Borg-Authorization": "Bearer invalid_token_here"},
        )

        assert response.status_code == 401

    def test_protected_endpoint_with_expired_token(self, test_client: TestClient):
        """Test accessing protected endpoint with expired token"""
        # Create a token with negative expiry (already expired)
        expired_token = create_access_token(
            data={"sub": "testuser"}, expires_delta=timedelta(minutes=-10)
        )

        response = test_client.get(
            "/api/auth/me", headers={"X-Borg-Authorization": f"Bearer {expired_token}"}
        )

        assert response.status_code == 401

    def test_protected_endpoint_missing_bearer_prefix(
        self, test_client: TestClient, auth_token
    ):
        """Test accessing protected endpoint without Bearer prefix"""
        response = test_client.get(
            "/api/auth/me",
            headers={"X-Borg-Authorization": auth_token},  # Missing "Bearer" prefix
        )

        assert response.status_code == 401

    def test_access_protected_endpoint_with_valid_token_succeeds(
        self, test_client: TestClient, admin_headers
    ):
        """Should allow access to protected endpoint with valid token"""
        response = test_client.get("/api/repositories/", headers=admin_headers)

        assert response.status_code == 200


@pytest.mark.unit
class TestPasswordSetupFlow:
    def test_skip_password_setup_clears_must_change_password(
        self, test_client: TestClient, admin_headers, admin_user, test_db
    ):
        admin_user.must_change_password = True
        test_db.commit()

        response = test_client.post(
            "/api/auth/password-setup/skip", headers=admin_headers
        )

        assert response.status_code == 200
        assert response.json()["must_change_password"] is False
        test_db.refresh(admin_user)
        assert admin_user.must_change_password is False

    def test_auth_change_password_clears_must_change_password(
        self, test_client: TestClient, admin_headers, admin_user, test_db
    ):
        admin_user.must_change_password = True
        test_db.commit()

        response = test_client.post(
            "/api/auth/change-password",
            json={"current_password": "admin123", "new_password": "NewPass123!"},
            headers=admin_headers,
        )

        assert response.status_code == 200
        test_db.refresh(admin_user)
        assert admin_user.must_change_password is False


@pytest.mark.unit
class TestPasskeyErrors:
    def test_passkey_registration_requires_user_verification(
        self, test_client: TestClient, admin_headers, admin_user, monkeypatch
    ):
        ceremony_token = create_passkey_ceremony_token(
            username=admin_user.username,
            challenge="challenge-123",
            purpose="passkey_register",
        )

        def fake_require_webauthn():
            class InvalidRegistrationResponse(Exception):
                pass

            def verify_registration_response(**kwargs):
                raise InvalidRegistrationResponse(
                    "User verification is required but user was not verified during attestation"
                )

            return {
                "parse_registration_credential_json": lambda value: value,
                "base64url_to_bytes": lambda value: value.encode("utf-8"),
                "verify_registration_response": verify_registration_response,
                "InvalidRegistrationResponse": InvalidRegistrationResponse,
            }

        monkeypatch.setattr("app.api.auth.require_webauthn", fake_require_webauthn)

        response = test_client.post(
            "/api/auth/passkeys/register/verify",
            headers=admin_headers,
            json={
                "ceremony_token": ceremony_token,
                "credential": {"id": "credential-123", "response": {}},
                "name": "Desk Mac",
            },
        )

        assert response.status_code == 400
        assert (
            response.json()["detail"]["key"]
            == "backend.errors.auth.passkeyUserVerificationRequired"
        )

    def test_passkey_registration_invalid_response_returns_invalid_passkey(
        self, test_client: TestClient, admin_headers, admin_user, monkeypatch
    ):
        ceremony_token = create_passkey_ceremony_token(
            username=admin_user.username,
            challenge="challenge-123",
            purpose="passkey_register",
        )

        def fake_require_webauthn():
            class InvalidRegistrationResponse(Exception):
                pass

            def verify_registration_response(**kwargs):
                raise InvalidRegistrationResponse("Registration response was invalid")

            return {
                "parse_registration_credential_json": lambda value: value,
                "base64url_to_bytes": lambda value: value.encode("utf-8"),
                "verify_registration_response": verify_registration_response,
                "InvalidRegistrationResponse": InvalidRegistrationResponse,
            }

        monkeypatch.setattr("app.api.auth.require_webauthn", fake_require_webauthn)

        response = test_client.post(
            "/api/auth/passkeys/register/verify",
            headers=admin_headers,
            json={
                "ceremony_token": ceremony_token,
                "credential": {"id": "credential-123", "response": {}},
                "name": "Desk Mac",
            },
        )

        assert response.status_code == 400
        assert response.json()["detail"]["key"] == "backend.errors.auth.invalidPasskey"

    def test_passkey_authentication_requires_user_verification(
        self, test_client: TestClient, test_db, test_user, monkeypatch
    ):
        passkey = PasskeyCredential(
            user_id=test_user.id,
            name="Desk Mac",
            credential_id="credential-123",
            public_key=base64.urlsafe_b64encode(b"public-key").decode("ascii"),
            sign_count=0,
        )
        test_db.add(passkey)
        test_db.commit()

        ceremony_token = create_passkey_ceremony_token(
            username="passkey-user",
            challenge="challenge-456",
            purpose="passkey_authenticate",
        )

        def fake_require_webauthn():
            class InvalidAuthenticationResponse(Exception):
                pass

            def verify_authentication_response(**kwargs):
                raise InvalidAuthenticationResponse(
                    "User verification is required but user was not verified during authentication"
                )

            return {
                "parse_authentication_credential_json": lambda value: value,
                "base64url_to_bytes": lambda value: value.encode("utf-8"),
                "verify_authentication_response": verify_authentication_response,
                "InvalidAuthenticationResponse": InvalidAuthenticationResponse,
            }

        monkeypatch.setattr("app.api.auth.require_webauthn", fake_require_webauthn)

        response = test_client.post(
            "/api/auth/passkeys/authenticate/verify",
            json={
                "ceremony_token": ceremony_token,
                "credential": {"id": "credential-123", "response": {}},
            },
        )

        assert response.status_code == 400
        assert (
            response.json()["detail"]["key"]
            == "backend.errors.auth.passkeyUserVerificationRequired"
        )

    def test_passkey_authentication_rate_limits_repeated_failures(
        self, test_client: TestClient, test_db, test_user, monkeypatch
    ):
        passkey = PasskeyCredential(
            user_id=test_user.id,
            name="Desk Mac",
            credential_id="credential-rate-limit",
            public_key=base64.urlsafe_b64encode(b"public-key").decode("ascii"),
            sign_count=0,
        )
        test_db.add(passkey)
        test_db.commit()

        ceremony_token = create_passkey_ceremony_token(
            username="passkey-user",
            challenge="challenge-rate-limit",
            purpose="passkey_authenticate",
        )

        def fake_require_webauthn():
            class InvalidAuthenticationResponse(Exception):
                pass

            def verify_authentication_response(**kwargs):
                raise InvalidAuthenticationResponse("invalid authentication response")

            return {
                "parse_authentication_credential_json": lambda value: value,
                "base64url_to_bytes": lambda value: value.encode("utf-8"),
                "verify_authentication_response": verify_authentication_response,
                "InvalidAuthenticationResponse": InvalidAuthenticationResponse,
            }

        monkeypatch.setattr("app.api.auth.require_webauthn", fake_require_webauthn)

        for _ in range(7):
            response = test_client.post(
                "/api/auth/passkeys/authenticate/verify",
                json={
                    "ceremony_token": ceremony_token,
                    "credential": {"id": "credential-rate-limit", "response": {}},
                },
            )
            assert response.status_code == 400

        limited_response = test_client.post(
            "/api/auth/passkeys/authenticate/verify",
            json={
                "ceremony_token": ceremony_token,
                "credential": {"id": "credential-rate-limit", "response": {}},
            },
        )
        assert limited_response.status_code == 429
        assert (
            limited_response.json()["detail"]["key"]
            == "backend.errors.auth.tooManyRequests"
        )


@pytest.mark.unit
class TestTokenValidation:
    """Test JWT token validation in protected endpoints"""

    def test_expired_token_returns_401(self, test_client: TestClient):
        """Should return 401 for expired token"""
        # Use a token that's clearly expired (past timestamp)
        expired_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJhZG1pbiIsImV4cCI6MTUxNjIzOTAyMn0.4Adcj0vVzR3aP_-3dFvmn3o9F3xqCKuXqCxBZu9cZqw"

        response = test_client.get(
            "/api/repositories/",
            headers={"X-Borg-Authorization": f"Bearer {expired_token}"},
        )

        assert response.status_code == 401

    def test_malformed_token_returns_401(self, test_client: TestClient):
        """Should return 401 for malformed token"""
        response = test_client.get(
            "/api/repositories/",
            headers={"X-Borg-Authorization": "Bearer not.a.valid.jwt"},
        )

        assert response.status_code == 401

    def test_missing_bearer_prefix_returns_403(self, test_client: TestClient):
        """
        Currently returns 403 when token doesn't have Bearer prefix.
        FastAPI's HTTPBearer validates the authorization scheme.
        """
        response = test_client.get(
            "/api/repositories/",
            headers={"X-Borg-Authorization": "InvalidPrefix token_here"},
        )

        assert response.status_code == 401


@pytest.mark.unit
class TestProxyAuthentication:
    """Test proxy authentication (DISABLE_AUTHENTICATION mode)"""

    def test_auth_config_endpoint_jwt_mode(self, test_client: TestClient):
        """Test auth config endpoint returns JWT mode by default"""
        response = test_client.get("/api/auth/config")

        assert response.status_code == 200
        data = response.json()
        assert "proxy_auth_enabled" in data
        assert "insecure_no_auth_enabled" in data
        assert "authentication_required" in data
        assert "proxy_auth_header" in data
        assert "proxy_auth_role_header" in data
        assert "proxy_auth_all_repositories_role_header" in data
        assert "proxy_auth_email_header" in data
        assert "proxy_auth_full_name_header" in data
        assert "proxy_auth_health" in data
        assert data["proxy_auth_enabled"] is False
        assert data["insecure_no_auth_enabled"] is False
        assert data["authentication_required"] is True
        assert data["proxy_auth_header"] is None
        assert data["proxy_auth_role_header"] is None
        assert data["proxy_auth_all_repositories_role_header"] is None
        assert data["proxy_auth_email_header"] is None
        assert data["proxy_auth_full_name_header"] is None
        assert data["proxy_auth_health"] == {"enabled": False, "warnings": []}

    def test_auth_config_endpoint_proxy_mode(
        self, test_client: TestClient, monkeypatch
    ):
        """Test auth config endpoint returns proxy mode when enabled"""
        from app import config

        monkeypatch.setattr(config.settings, "disable_authentication", True)

        response = test_client.get("/api/auth/config")

        assert response.status_code == 200
        data = response.json()
        assert data["proxy_auth_enabled"] is True
        assert data["insecure_no_auth_enabled"] is False
        assert data["authentication_required"] is False
        assert data["proxy_auth_header"] == "X-Forwarded-User"
        assert data["proxy_auth_role_header"] is None
        assert data["proxy_auth_all_repositories_role_header"] is None
        assert data["proxy_auth_email_header"] is None
        assert data["proxy_auth_full_name_header"] is None
        assert data["proxy_auth_health"]["enabled"] is True

    def test_auth_config_endpoint_insecure_no_auth_mode(
        self, test_client: TestClient, monkeypatch
    ):
        """Test auth config endpoint exposes insecure no-auth mode separately."""
        from app import config

        monkeypatch.setattr(config.settings, "allow_insecure_no_auth", True)
        monkeypatch.setattr(config.settings, "disable_authentication", True)

        response = test_client.get("/api/auth/config")

        assert response.status_code == 200
        data = response.json()
        assert data["proxy_auth_enabled"] is False
        assert data["insecure_no_auth_enabled"] is True
        assert data["authentication_required"] is False
        assert data["proxy_auth_header"] is None
        assert data["proxy_auth_health"] == {"enabled": False, "warnings": []}

    def test_insecure_no_auth_uses_local_admin_without_proxy_header(
        self, test_client: TestClient, test_db, monkeypatch
    ):
        """In insecure mode, protected endpoints should resolve to a local user without headers."""
        from app import config
        from app.database.models import User
        from app.core.security import get_password_hash

        monkeypatch.setattr(config.settings, "allow_insecure_no_auth", True)
        test_db.add(
            User(
                username="admin",
                password_hash=get_password_hash("admin123"),
                email="admin@example.com",
                is_active=True,
                role="admin",
                must_change_password=False,
            )
        )
        test_db.commit()

        response = test_client.get("/api/auth/me")

        assert response.status_code == 200
        data = response.json()
        assert data["username"] == "admin"
        assert data["role"] == "admin"

    def test_proxy_auth_with_header(
        self, test_client: TestClient, test_db, monkeypatch
    ):
        """Test proxy auth with X-Forwarded-User header auto-creates and logs in user"""
        from app import config

        monkeypatch.setattr(config.settings, "disable_authentication", True)

        # Access protected endpoint with proxy header
        response = test_client.get(
            "/api/auth/me", headers={"X-Forwarded-User": "proxyuser"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["username"] == "proxyuser"
        assert data["role"] == "viewer"

        # Verify user was created in database
        from app.database.models import User

        user = test_db.query(User).filter(User.username == "proxyuser").first()
        assert user is not None
        assert user.username == "proxyuser"
        assert user.email == "proxyuser@proxy.local"
        assert user.password_hash == ""  # No password for proxy auth users

    def test_proxy_auth_without_header_is_denied(
        self, test_client: TestClient, test_db, monkeypatch
    ):
        """Test proxy auth fails closed when no trusted identity header is present"""
        from app import config

        monkeypatch.setattr(config.settings, "disable_authentication", True)

        # Access without any proxy header
        response = test_client.get("/api/auth/me")

        assert response.status_code == 401
        data = response.json()
        assert data["detail"]["key"] == "backend.errors.auth.proxyHeaderRequired"
        assert data["detail"]["params"]["header"] == "X-Forwarded-User"

    def test_proxy_auth_with_alternative_headers(
        self, test_client: TestClient, test_db, monkeypatch
    ):
        """Test proxy auth tries alternative common headers"""
        from app import config

        monkeypatch.setattr(config.settings, "disable_authentication", True)

        # Test with X-Remote-User header (used by Authelia)
        response = test_client.get(
            "/api/auth/me", headers={"X-Remote-User": "authelia_user"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["username"] == "authelia_user"

        # Test with Remote-User header
        response = test_client.get(
            "/api/auth/me", headers={"Remote-User": "nginx_user"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["username"] == "nginx_user"

        # Test with X-authentik-username (Authentik specific)
        response = test_client.get(
            "/api/auth/me", headers={"X-authentik-username": "authentik_user"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["username"] == "authentik_user"

    def test_proxy_auth_custom_header_disables_fallback_headers(
        self, test_client: TestClient, monkeypatch
    ):
        """A custom configured identity header should be the only trusted username source."""
        from app import config

        monkeypatch.setattr(config.settings, "disable_authentication", True)
        monkeypatch.setattr(config.settings, "proxy_auth_header", "X-Custom-User")

        response = test_client.get(
            "/api/auth/me", headers={"X-Forwarded-User": "fallback-user"}
        )

        assert response.status_code == 401
        data = response.json()
        assert data["detail"]["key"] == "backend.errors.auth.proxyHeaderRequired"
        assert data["detail"]["params"]["header"] == "X-Custom-User"

    def test_proxy_auth_username_normalized_lowercase(
        self, test_client: TestClient, test_db, monkeypatch
    ):
        """Test proxy auth normalizes username to lowercase"""
        from app import config

        monkeypatch.setattr(config.settings, "disable_authentication", True)

        response = test_client.get(
            "/api/auth/me", headers={"X-Forwarded-User": "JohnDoe"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["username"] == "johndoe"  # Normalized to lowercase

    def test_proxy_auth_reuses_existing_user(
        self, test_client: TestClient, test_db, monkeypatch
    ):
        """Test proxy auth reuses existing user instead of creating duplicate"""
        from app import config
        from app.database.models import User
        from app.core.security import get_password_hash

        # Create user first
        existing_user = User(
            username="existinguser",
            password_hash=get_password_hash("somepassword"),
            email="existing@example.com",
            is_active=True,
            role="admin",
        )
        test_db.add(existing_user)
        test_db.commit()
        user_id = existing_user.id

        monkeypatch.setattr(config.settings, "disable_authentication", True)

        # Access with same username via proxy
        response = test_client.get(
            "/api/auth/me", headers={"X-Forwarded-User": "existinguser"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["username"] == "existinguser"
        assert data["role"] == "admin"  # Preserved from original user
        assert data["email"] == "existing@example.com"  # Preserved

        # Verify no duplicate was created
        users = test_db.query(User).filter(User.username == "existinguser").all()
        assert len(users) == 1
        assert users[0].id == user_id  # Same user

    def test_proxy_auth_inactive_user_denied(
        self, test_client: TestClient, test_db, monkeypatch
    ):
        """Test proxy auth denies access to inactive users"""
        from app import config
        from app.database.models import User

        # Create inactive user
        inactive_user = User(
            username="inactiveuser",
            password_hash="",
            email="inactive@proxy.local",
            is_active=False,
            role="viewer",
        )
        test_db.add(inactive_user)
        test_db.commit()

        monkeypatch.setattr(config.settings, "disable_authentication", True)

        response = test_client.get(
            "/api/auth/me", headers={"X-Forwarded-User": "inactiveuser"}
        )

        assert response.status_code == 403
        assert "disabled" in response.json()["detail"].lower()

    def test_jwt_auth_still_works_when_proxy_disabled(
        self, test_client: TestClient, admin_headers
    ):
        """Test that JWT auth still works normally when proxy auth is disabled"""
        # Proxy auth disabled by default, should use JWT
        response = test_client.get("/api/auth/me", headers=admin_headers)

        # Should work with JWT token
        assert response.status_code == 200

    def test_proxy_auth_custom_header_configuration(
        self, test_client: TestClient, test_db, monkeypatch
    ):
        """Test proxy auth with custom configured header"""
        from app import config

        monkeypatch.setattr(config.settings, "disable_authentication", True)
        monkeypatch.setattr(config.settings, "proxy_auth_header", "X-Custom-User")

        response = test_client.get(
            "/api/auth/me", headers={"X-Custom-User": "customuser"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["username"] == "customuser"

    def test_proxy_auth_updates_last_login(
        self, test_client: TestClient, test_db, monkeypatch
    ):
        """Test proxy auth updates last_login timestamp"""
        from app import config
        from app.database.models import User
        import time

        monkeypatch.setattr(config.settings, "disable_authentication", True)

        # First access
        response = test_client.get(
            "/api/auth/me", headers={"X-Forwarded-User": "timeuser"}
        )
        assert response.status_code == 200

        user = test_db.query(User).filter(User.username == "timeuser").first()
        first_login = user.last_login

        time.sleep(1)  # Wait a second

        # Second access
        response = test_client.get(
            "/api/auth/me", headers={"X-Forwarded-User": "timeuser"}
        )
        assert response.status_code == 200

        test_db.refresh(user)
        second_login = user.last_login

        # Last login should be updated
        assert second_login > first_login

    def test_proxy_auth_can_assign_role_from_trusted_header(
        self, test_client: TestClient, test_db, monkeypatch
    ):
        from app import config
        from app.database.models import User

        monkeypatch.setattr(config.settings, "disable_authentication", True)
        monkeypatch.setattr(config.settings, "proxy_auth_role_header", "X-Proxy-Role")

        response = test_client.get(
            "/api/auth/me",
            headers={"X-Forwarded-User": "operatoruser", "X-Proxy-Role": "operator"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["role"] == "operator"
        assert data["all_repositories_role"] == "operator"

        user = test_db.query(User).filter(User.username == "operatoruser").first()
        assert user is not None
        assert user.role == "operator"
        assert user.all_repositories_role == "operator"

    def test_proxy_auth_can_assign_all_repositories_role_from_trusted_header(
        self, test_client: TestClient, monkeypatch
    ):
        from app import config

        monkeypatch.setattr(config.settings, "disable_authentication", True)
        monkeypatch.setattr(config.settings, "proxy_auth_role_header", "X-Proxy-Role")
        monkeypatch.setattr(
            config.settings,
            "proxy_auth_all_repositories_role_header",
            "X-Proxy-Repo-Role",
        )

        response = test_client.get(
            "/api/auth/me",
            headers={
                "X-Forwarded-User": "adminuser",
                "X-Proxy-Role": "admin",
                "X-Proxy-Repo-Role": "operator",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["role"] == "admin"
        assert data["all_repositories_role"] == "operator"

    def test_proxy_auth_can_assign_email_and_full_name_from_trusted_headers(
        self, test_client: TestClient, test_db, monkeypatch
    ):
        from app import config
        from app.database.models import User

        monkeypatch.setattr(config.settings, "disable_authentication", True)
        monkeypatch.setattr(config.settings, "proxy_auth_email_header", "X-Proxy-Email")
        monkeypatch.setattr(
            config.settings, "proxy_auth_full_name_header", "X-Proxy-Full-Name"
        )

        response = test_client.get(
            "/api/auth/me",
            headers={
                "X-Forwarded-User": "personuser",
                "X-Proxy-Email": "person@example.com",
                "X-Proxy-Full-Name": "Person Example",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["email"] == "person@example.com"
        assert data["full_name"] == "Person Example"

        user = test_db.query(User).filter(User.username == "personuser").first()
        assert user is not None
        assert user.email == "person@example.com"
        assert user.full_name == "Person Example"

    def test_proxy_auth_updates_existing_user_identity_from_trusted_headers(
        self, test_client: TestClient, test_db, monkeypatch
    ):
        from app import config
        from app.database.models import User

        existing_user = User(
            username="identityuser",
            password_hash="",
            email="old@proxy.local",
            full_name="Old Name",
            is_active=True,
            role="viewer",
        )
        test_db.add(existing_user)
        test_db.commit()

        monkeypatch.setattr(config.settings, "disable_authentication", True)
        monkeypatch.setattr(config.settings, "proxy_auth_email_header", "X-Proxy-Email")
        monkeypatch.setattr(
            config.settings, "proxy_auth_full_name_header", "X-Proxy-Full-Name"
        )

        response = test_client.get(
            "/api/auth/me",
            headers={
                "X-Forwarded-User": "identityuser",
                "X-Proxy-Email": "new@example.com",
                "X-Proxy-Full-Name": "New Name",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["email"] == "new@example.com"
        assert data["full_name"] == "New Name"

    def test_proxy_auth_ignores_email_header_when_already_taken(
        self, test_client: TestClient, test_db, monkeypatch
    ):
        from app import config
        from app.database.models import User

        test_db.add(
            User(
                username="existingowner",
                password_hash="",
                email="taken@example.com",
                is_active=True,
                role="viewer",
            )
        )
        test_db.commit()

        monkeypatch.setattr(config.settings, "disable_authentication", True)
        monkeypatch.setattr(config.settings, "proxy_auth_email_header", "X-Proxy-Email")

        response = test_client.get(
            "/api/auth/me",
            headers={
                "X-Forwarded-User": "emailconflictuser",
                "X-Proxy-Email": "taken@example.com",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["email"] == "emailconflictuser@proxy.local"

    def test_proxy_auth_ignores_invalid_role_header_values(
        self, test_client: TestClient, test_db, monkeypatch
    ):
        from app import config
        from app.database.models import User

        monkeypatch.setattr(config.settings, "disable_authentication", True)
        monkeypatch.setattr(config.settings, "proxy_auth_role_header", "X-Proxy-Role")
        monkeypatch.setattr(
            config.settings,
            "proxy_auth_all_repositories_role_header",
            "X-Proxy-Repo-Role",
        )

        response = test_client.get(
            "/api/auth/me",
            headers={
                "X-Forwarded-User": "invalidroleuser",
                "X-Proxy-Role": "superadmin",
                "X-Proxy-Repo-Role": "editor",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["role"] == "viewer"
        assert data["all_repositories_role"] == "viewer"

        user = test_db.query(User).filter(User.username == "invalidroleuser").first()
        assert user is not None
        assert user.role == "viewer"
        assert user.all_repositories_role == "viewer"

    def test_proxy_auth_updates_existing_user_role_from_trusted_header(
        self, test_client: TestClient, test_db, monkeypatch
    ):
        from app import config
        from app.database.models import User

        existing_user = User(
            username="mappeduser",
            password_hash="",
            email="mapped@proxy.local",
            is_active=True,
            role="viewer",
            all_repositories_role="viewer",
        )
        test_db.add(existing_user)
        test_db.commit()

        monkeypatch.setattr(config.settings, "disable_authentication", True)
        monkeypatch.setattr(config.settings, "proxy_auth_role_header", "X-Proxy-Role")

        response = test_client.get(
            "/api/auth/me",
            headers={"X-Forwarded-User": "mappeduser", "X-Proxy-Role": "operator"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["role"] == "operator"
        assert data["all_repositories_role"] == "operator"


@pytest.mark.unit
class TestDualHeaderFallback:
    """Test that both X-Borg-Authorization and legacy Authorization headers are accepted"""

    def test_legacy_authorization_header_still_works(
        self, test_client: TestClient, admin_token
    ):
        """Legacy Authorization header should still be accepted for backward compatibility"""
        response = test_client.get(
            "/api/repositories/", headers={"Authorization": f"Bearer {admin_token}"}
        )

        assert response.status_code in [200, 204]

    def test_x_borg_authorization_takes_precedence(
        self, test_client: TestClient, admin_token
    ):
        """X-Borg-Authorization should take precedence over Authorization"""
        response = test_client.get(
            "/api/repositories/",
            headers={
                "X-Borg-Authorization": f"Bearer {admin_token}",
                "Authorization": "Bearer invalid_token_here",
            },
        )

        assert response.status_code in [200, 204]

    def test_invalid_x_borg_does_not_fall_back_to_valid_authorization(
        self, test_client: TestClient, admin_token
    ):
        """When X-Borg-Authorization is present but invalid, it should NOT fall back to Authorization"""
        response = test_client.get(
            "/api/repositories/",
            headers={
                "X-Borg-Authorization": "Bearer invalid_token_here",
                "Authorization": f"Bearer {admin_token}",
            },
        )

        assert response.status_code == 401


@pytest.mark.unit
class TestTotpAuthentication:
    def test_login_returns_totp_challenge_for_enabled_user(
        self, test_client: TestClient, test_db
    ):
        secret = "JBSWY3DPEHPK3PXP"
        user = User(
            username="totpuser",
            password_hash=get_password_hash("password123"),
            is_active=True,
            role="viewer",
            totp_enabled=True,
            totp_secret_encrypted=encrypt_secret(secret),
            totp_recovery_codes_hashes="[]",
        )
        test_db.add(user)
        test_db.commit()

        response = test_client.post(
            "/api/auth/login",
            data={"username": "totpuser", "password": "password123"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["totp_required"] is True
        assert data["login_challenge_token"]
        assert data["access_token"] is None

    def test_login_totp_completion_accepts_current_code(
        self, test_client: TestClient, test_db
    ):
        import time

        secret = "JBSWY3DPEHPK3PXP"
        user = User(
            username="totpuser2",
            password_hash=get_password_hash("password123"),
            is_active=True,
            role="viewer",
            totp_enabled=True,
            totp_secret_encrypted=encrypt_secret(secret),
            totp_recovery_codes_hashes="[]",
        )
        test_db.add(user)
        test_db.commit()

        login_response = test_client.post(
            "/api/auth/login",
            data={"username": "totpuser2", "password": "password123"},
        )
        challenge_token = login_response.json()["login_challenge_token"]
        code = _hotp(secret, int(time.time()) // 30)

        response = test_client.post(
            "/api/auth/login/totp",
            json={"login_challenge_token": challenge_token, "code": code},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["access_token"]
        assert data["totp_required"] is False

    def test_login_totp_rate_limits_repeated_invalid_codes(
        self, test_client: TestClient, test_db
    ):
        secret = "JBSWY3DPEHPK3PXP"
        user = User(
            username="totpratelimit",
            password_hash=get_password_hash("password123"),
            is_active=True,
            role="viewer",
            totp_enabled=True,
            totp_secret_encrypted=encrypt_secret(secret),
            totp_recovery_codes_hashes="[]",
        )
        test_db.add(user)
        test_db.commit()

        login_response = test_client.post(
            "/api/auth/login",
            data={"username": "totpratelimit", "password": "password123"},
        )
        challenge_token = login_response.json()["login_challenge_token"]

        for _ in range(4):
            response = test_client.post(
                "/api/auth/login/totp",
                json={"login_challenge_token": challenge_token, "code": "000000"},
            )
            assert response.status_code == 401

        limited_response = test_client.post(
            "/api/auth/login/totp",
            json={"login_challenge_token": challenge_token, "code": "000000"},
        )
        assert limited_response.status_code == 429
        assert (
            limited_response.json()["detail"]["key"]
            == "backend.errors.auth.tooManyRequests"
        )

    def test_totp_setup_enable_and_disable_flow(
        self, test_client: TestClient, admin_headers, test_db
    ):
        import time

        setup_response = test_client.post(
            "/api/auth/totp/setup",
            headers=admin_headers,
            json={"current_password": "admin123"},
        )
        assert setup_response.status_code == 200
        setup_data = setup_response.json()
        assert setup_data["setup_token"]
        assert setup_data["secret"]
        assert len(setup_data["recovery_codes"]) == 8

        enable_code = _hotp(setup_data["secret"], int(time.time()) // 30)
        enable_response = test_client.post(
            "/api/auth/totp/enable",
            headers=admin_headers,
            json={"setup_token": setup_data["setup_token"], "code": enable_code},
        )
        assert enable_response.status_code == 200
        assert enable_response.json()["enabled"] is True

        admin_user = test_db.query(User).filter(User.username == "admin").first()
        assert admin_user.totp_enabled is True
        assert admin_user.totp_secret_encrypted

        disable_response = test_client.post(
            "/api/auth/totp/disable",
            headers=admin_headers,
            json={
                "current_password": "admin123",
                "code": setup_data["recovery_codes"][0],
            },
        )
        assert disable_response.status_code == 200

        test_db.refresh(admin_user)
        assert admin_user.totp_enabled is False
        assert admin_user.totp_secret_encrypted is None


@pytest.mark.unit
class TestOidcAuthentication:
    def _oidc_provider(self, *, token_auth_method: str = "client_secret_post"):
        from app.core.oidc import OidcProviderConfiguration

        return OidcProviderConfiguration(
            provider_name="Test OIDC",
            discovery_url="https://id.example.com/.well-known/openid-configuration",
            client_id="borg-ui",
            client_secret="secret-value",
            token_auth_method=token_auth_method,
            authorization_endpoint="https://id.example.com/auth",
            token_endpoint="https://id.example.com/token",
            userinfo_endpoint="https://id.example.com/userinfo",
            jwks_uri="https://id.example.com/jwks",
            issuer="https://id.example.com",
            scopes="openid profile email",
            redirect_uri="http://testserver/api/auth/oidc/callback",
            end_session_endpoint="https://id.example.com/logout",
            username_claim="preferred_username",
            email_claim="email",
            full_name_claim="name",
            group_claim=None,
            role_claim=None,
            admin_groups=[],
            all_repositories_role_claim=None,
            new_user_mode="viewer",
            new_user_template_username=None,
            default_role="viewer",
            default_all_repositories_role="viewer",
        )

    def test_oidc_id_token_requires_sub_exp_and_iat(self, monkeypatch):
        from app.core.oidc import verify_id_token

        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

        class DummyJwkClient:
            def __init__(self, jwks_uri):
                self.jwks_uri = jwks_uri

            def get_signing_key_from_jwt(self, token):
                class SigningKey:
                    key = private_key.public_key()

                return SigningKey()

        monkeypatch.setattr("app.core.oidc.PyJWKClient", DummyJwkClient)
        provider = self._oidc_provider()
        now = datetime.now(timezone.utc)
        required_claims = {
            "iss": provider.issuer,
            "aud": provider.client_id,
            "sub": "subject-123",
            "iat": now,
            "exp": now + timedelta(minutes=5),
            "nonce": "nonce-123",
        }

        for missing_claim in ("sub", "exp", "iat"):
            claims = dict(required_claims)
            claims.pop(missing_claim)
            id_token = jwt.encode(claims, private_key, algorithm="RS256")

            with pytest.raises(Exception):
                verify_id_token(provider, id_token, nonce="nonce-123")

    @pytest.mark.asyncio
    async def test_oidc_token_exchange_uses_client_secret_basic(self, monkeypatch):
        from app.core.oidc import exchange_code_for_tokens

        captured = {}

        class FakeResponse:
            def raise_for_status(self):
                return None

            def json(self):
                return {"access_token": "access-token", "id_token": "id-token"}

        class FakeAsyncClient:
            def __init__(self, timeout):
                self.timeout = timeout

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return None

            async def post(self, url, *, data, headers):
                captured["url"] = url
                captured["data"] = data
                captured["headers"] = headers
                return FakeResponse()

        monkeypatch.setattr("app.core.oidc.httpx.AsyncClient", FakeAsyncClient)
        provider = self._oidc_provider(token_auth_method="client_secret_basic")

        response = await exchange_code_for_tokens(
            provider, code="auth-code", code_verifier="verifier"
        )

        assert response["access_token"] == "access-token"
        assert captured["data"]["client_id"] == "borg-ui"
        assert "client_secret" not in captured["data"]
        assert captured["headers"]["Authorization"].startswith("Basic ")

    def test_auth_config_endpoint_includes_oidc_settings(
        self, test_client: TestClient, test_db
    ):
        test_db.add(
            SystemSettings(
                oidc_enabled=True,
                oidc_provider_name="Authentik",
                oidc_disable_local_auth=True,
                oidc_discovery_url="https://id.example.com/.well-known/openid-configuration",
                oidc_client_id="borg-ui",
                oidc_client_secret_encrypted=encrypt_secret("secret-value"),
            )
        )
        test_db.commit()

        response = test_client.get("/api/auth/config")

        assert response.status_code == 200
        data = response.json()
        assert data["oidc_enabled"] is True
        assert data["oidc_provider_name"] == "Authentik"
        assert data["oidc_disable_local_auth"] is True
        assert data["oidc_link_supported"] is True
        assert data["oidc_unlink_supported"] is True
        assert data["oidc_account_linking_supported"] is True

    def test_oidc_link_start_returns_authorization_url(
        self, test_client: TestClient, test_db, admin_headers, monkeypatch
    ):
        test_db.add(
            SystemSettings(
                oidc_enabled=True,
                oidc_discovery_url="https://id.example.com/.well-known/openid-configuration",
                oidc_client_id="borg-ui",
                oidc_client_secret_encrypted=encrypt_secret("secret-value"),
            )
        )
        test_db.commit()

        async def fake_discover(*args, **kwargs):
            return self._oidc_provider()

        monkeypatch.setattr("app.api.auth.discover_oidc_configuration", fake_discover)

        response = test_client.post(
            "/api/auth/oidc/link",
            headers=admin_headers,
            json={"return_to": "http://testserver/settings/account"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["authorization_url"].startswith("https://id.example.com/auth?")

        login_state = test_db.query(OidcLoginState).one()
        admin = test_db.query(User).filter(User.username == "admin").one()
        assert login_state.flow == "link"
        assert login_state.user_id == admin.id
        assert login_state.return_to == "http://testserver/settings/account"

    def test_local_login_is_blocked_when_oidc_disables_local_auth(
        self, test_client: TestClient, test_db
    ):
        test_db.add(
            SystemSettings(
                oidc_enabled=True,
                oidc_disable_local_auth=True,
                oidc_discovery_url="https://id.example.com/.well-known/openid-configuration",
                oidc_client_id="borg-ui",
                oidc_client_secret_encrypted=encrypt_secret("secret-value"),
            )
        )
        test_db.commit()

        response = test_client.post(
            "/api/auth/login",
            data={"username": "admin", "password": "admin123"},
        )

        assert response.status_code == 403
        assert (
            response.json()["detail"]["key"] == "backend.errors.auth.localLoginDisabled"
        )

    def test_totp_completion_is_blocked_when_oidc_disables_local_auth(
        self, test_client: TestClient, test_db
    ):
        challenge_user = User(
            username="totp-blocked-user",
            password_hash=get_password_hash("password123"),
            email="totp-blocked@example.com",
            role="viewer",
            is_active=True,
            totp_enabled=True,
        )
        test_db.add(challenge_user)
        test_db.add(
            SystemSettings(
                oidc_enabled=True,
                oidc_disable_local_auth=True,
                oidc_discovery_url="https://id.example.com/.well-known/openid-configuration",
                oidc_client_id="borg-ui",
                oidc_client_secret_encrypted=encrypt_secret("secret-value"),
            )
        )
        test_db.commit()

        from app.core.security import create_login_challenge_token

        response = test_client.post(
            "/api/auth/login/totp",
            json={
                "login_challenge_token": create_login_challenge_token(
                    challenge_user.username
                ),
                "code": "123456",
            },
        )

        assert response.status_code == 403
        assert (
            response.json()["detail"]["key"] == "backend.errors.auth.localLoginDisabled"
        )

    def test_passkey_completion_is_blocked_when_oidc_disables_local_auth(
        self, test_client: TestClient, test_db
    ):
        test_db.add(
            SystemSettings(
                oidc_enabled=True,
                oidc_disable_local_auth=True,
                oidc_discovery_url="https://id.example.com/.well-known/openid-configuration",
                oidc_client_id="borg-ui",
                oidc_client_secret_encrypted=encrypt_secret("secret-value"),
            )
        )
        test_db.commit()

        response = test_client.post(
            "/api/auth/passkeys/authenticate/verify",
            json={"ceremony_token": "invalid", "credential": {"id": "dummy"}},
        )

        assert response.status_code == 403
        assert (
            response.json()["detail"]["key"] == "backend.errors.auth.localLoginDisabled"
        )

    def test_oidc_exchange_creates_user_with_default_role(
        self, test_client: TestClient, test_db
    ):
        test_db.add(
            SystemSettings(
                oidc_enabled=True,
                oidc_provider_name="Authentik",
                oidc_discovery_url="https://id.example.com/.well-known/openid-configuration",
                oidc_client_id="borg-ui",
                oidc_client_secret_encrypted=encrypt_secret("secret-value"),
                oidc_default_role="operator",
                oidc_default_all_repositories_role="operator",
            )
        )
        test_db.commit()

        create_test_oidc_exchange_grant(
            test_db,
            username="oidc-user",
            oidc_subject="subject-123",
            email="oidc-user@example.com",
            full_name="OIDC User",
        )
        test_client.cookies.set("oidc_exchange_grant", "grant-123")

        response = test_client.post(
            "/api/auth/oidc/exchange",
            headers={"Origin": "http://testserver"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["access_token"]

        user = test_db.query(User).filter(User.username == "oidc-user").first()
        assert user is not None
        assert user.email == "oidc-user@example.com"
        assert user.full_name == "OIDC User"
        assert user.auth_source == "oidc"
        assert user.oidc_subject == "subject-123"
        assert user.oidc_last_id_token_encrypted is not None
        assert user.role == "operator"
        assert user.all_repositories_role == "operator"

    def test_oidc_exchange_links_existing_oidc_user_without_subject(
        self, test_client: TestClient, test_db
    ):
        existing_user = User(
            username="existing-oidc-user",
            password_hash="",
            email="existing-oidc@example.com",
            role="viewer",
            is_active=True,
            auth_source="oidc",
            oidc_subject=None,
        )
        test_db.add(existing_user)
        test_db.add(
            SystemSettings(
                oidc_enabled=True,
                oidc_discovery_url="https://id.example.com/.well-known/openid-configuration",
                oidc_client_id="borg-ui",
                oidc_client_secret_encrypted=encrypt_secret("secret-value"),
            )
        )
        test_db.commit()
        test_db.refresh(existing_user)

        create_test_oidc_exchange_grant(
            test_db,
            username="existing-oidc-user",
            oidc_subject="linked-subject",
            email="existing-oidc@example.com",
        )
        test_client.cookies.set("oidc_exchange_grant", "grant-123")

        response = test_client.post(
            "/api/auth/oidc/exchange", headers={"Origin": "http://testserver"}
        )

        assert response.status_code == 200
        test_db.refresh(existing_user)
        assert existing_user.oidc_subject == "linked-subject"
        assert existing_user.last_login is not None

    def test_oidc_exchange_rejects_subject_collision_on_existing_oidc_user(
        self, test_client: TestClient, test_db
    ):
        existing_user = User(
            username="existing-oidc-user",
            password_hash="",
            email="existing-oidc@example.com",
            role="viewer",
            is_active=True,
            auth_source="oidc",
            oidc_subject="original-subject",
        )
        test_db.add(existing_user)
        test_db.add(
            SystemSettings(
                oidc_enabled=True,
                oidc_discovery_url="https://id.example.com/.well-known/openid-configuration",
                oidc_client_id="borg-ui",
                oidc_client_secret_encrypted=encrypt_secret("secret-value"),
            )
        )
        test_db.commit()

        create_test_oidc_exchange_grant(
            test_db,
            username="existing-oidc-user",
            oidc_subject="different-subject",
            email="existing-oidc@example.com",
        )
        test_client.cookies.set("oidc_exchange_grant", "grant-123")

        response = test_client.post(
            "/api/auth/oidc/exchange", headers={"Origin": "http://testserver"}
        )

        assert response.status_code == 409
        assert (
            response.json()["detail"]["key"]
            == "backend.errors.auth.oidcIdentityConflict"
        )

    def test_oidc_exchange_requires_same_origin_request(
        self, test_client: TestClient, test_db
    ):
        test_db.add(
            SystemSettings(
                oidc_enabled=True,
                oidc_discovery_url="https://id.example.com/.well-known/openid-configuration",
                oidc_client_id="borg-ui",
                oidc_client_secret_encrypted=encrypt_secret("secret-value"),
            )
        )
        test_db.commit()

        create_test_oidc_exchange_grant(test_db)
        test_client.cookies.set("oidc_exchange_grant", "grant-123")

        response = test_client.post("/api/auth/oidc/exchange")

        assert response.status_code == 403
        assert (
            response.json()["detail"]["key"]
            == "backend.errors.auth.invalidAuthentication"
        )

    def test_oidc_exchange_grant_is_single_use(self, test_client: TestClient, test_db):
        test_db.add(
            SystemSettings(
                oidc_enabled=True,
                oidc_discovery_url="https://id.example.com/.well-known/openid-configuration",
                oidc_client_id="borg-ui",
                oidc_client_secret_encrypted=encrypt_secret("secret-value"),
            )
        )
        test_db.commit()

        create_test_oidc_exchange_grant(test_db)
        test_client.cookies.set("oidc_exchange_grant", "grant-123")

        first = test_client.post(
            "/api/auth/oidc/exchange", headers={"Origin": "http://testserver"}
        )
        assert first.status_code == 200

        second = test_client.post(
            "/api/auth/oidc/exchange", headers={"Origin": "http://testserver"}
        )
        assert second.status_code == 401

    def test_expired_oidc_artifacts_are_pruned(self, test_db):
        from app.api.auth import _prune_expired_oidc_artifacts

        expired_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        valid_until = datetime.now(timezone.utc) + timedelta(minutes=5)
        test_db.add(
            OidcLoginState(
                state_id="expired-state",
                nonce="nonce",
                code_verifier="verifier",
                return_to="http://testserver/login",
                expires_at=expired_at,
            )
        )
        test_db.add(
            OidcExchangeGrant(
                grant_id="expired-grant",
                username="expired-user",
                expires_at=expired_at,
            )
        )
        test_db.add(
            OidcExchangeGrant(
                grant_id="valid-grant",
                username="valid-user",
                expires_at=valid_until,
            )
        )
        test_db.commit()

        _prune_expired_oidc_artifacts(test_db)

        assert (
            test_db.query(OidcLoginState)
            .filter(OidcLoginState.state_id == "expired-state")
            .first()
            is None
        )
        assert (
            test_db.query(OidcExchangeGrant)
            .filter(OidcExchangeGrant.grant_id == "expired-grant")
            .first()
            is None
        )
        assert (
            test_db.query(OidcExchangeGrant)
            .filter(OidcExchangeGrant.grant_id == "valid-grant")
            .first()
            is not None
        )

    def test_oidc_exchange_rejects_username_collision_with_local_user(
        self, test_client: TestClient, test_db
    ):
        test_db.add(
            User(
                username="existing-local-user",
                password_hash=get_password_hash("password123"),
                email="existing-local@example.com",
                role="viewer",
                is_active=True,
                auth_source="local",
            )
        )
        test_db.add(
            SystemSettings(
                oidc_enabled=True,
                oidc_discovery_url="https://id.example.com/.well-known/openid-configuration",
                oidc_client_id="borg-ui",
                oidc_client_secret_encrypted=encrypt_secret("secret-value"),
            )
        )
        test_db.commit()

        create_test_oidc_exchange_grant(
            test_db,
            username="existing-local-user",
            oidc_subject="subject-local-collision",
            email="new-oidc@example.com",
        )
        test_client.cookies.set("oidc_exchange_grant", "grant-123")

        response = test_client.post(
            "/api/auth/oidc/exchange", headers={"Origin": "http://testserver"}
        )

        assert response.status_code == 409
        assert (
            response.json()["detail"]["key"]
            == "backend.errors.auth.oidcAccountLinkRequired"
        )

    def test_oidc_exchange_rejects_email_collision(
        self, test_client: TestClient, test_db
    ):
        test_db.add(
            User(
                username="existing-user",
                password_hash=get_password_hash("password123"),
                email="shared@example.com",
                role="viewer",
                is_active=True,
                auth_source="oidc",
                oidc_subject="subject-existing",
            )
        )
        test_db.add(
            SystemSettings(
                oidc_enabled=True,
                oidc_discovery_url="https://id.example.com/.well-known/openid-configuration",
                oidc_client_id="borg-ui",
                oidc_client_secret_encrypted=encrypt_secret("secret-value"),
            )
        )
        test_db.commit()

        create_test_oidc_exchange_grant(
            test_db,
            username="new-oidc-user",
            oidc_subject="subject-email-collision",
            email="shared@example.com",
        )
        test_client.cookies.set("oidc_exchange_grant", "grant-123")

        response = test_client.post(
            "/api/auth/oidc/exchange", headers={"Origin": "http://testserver"}
        )

        assert response.status_code == 409
        assert (
            response.json()["detail"]["key"]
            == "backend.errors.auth.oidcEmailAlreadyInUse"
        )

    def test_oidc_exchange_pending_mode_creates_inactive_user_and_denies_login(
        self, test_client: TestClient, test_db
    ):
        test_db.add(
            SystemSettings(
                oidc_enabled=True,
                oidc_discovery_url="https://id.example.com/.well-known/openid-configuration",
                oidc_client_id="borg-ui",
                oidc_client_secret_encrypted=encrypt_secret("secret-value"),
                oidc_new_user_mode="pending",
            )
        )
        test_db.commit()

        create_test_oidc_exchange_grant(
            test_db,
            username="pending-user",
            oidc_subject="subject-pending",
            email="pending-user@example.com",
            full_name="Pending User",
        )
        test_client.cookies.set("oidc_exchange_grant", "grant-123")

        response = test_client.post(
            "/api/auth/oidc/exchange",
            headers={"Origin": "http://testserver"},
        )

        assert response.status_code == 403
        assert (
            response.json()["detail"]["key"]
            == "backend.errors.auth.oidcPendingApproval"
        )

        user = test_db.query(User).filter(User.username == "pending-user").first()
        assert user is not None
        assert user.is_active is False

    def test_oidc_admin_role_claim_requires_matching_admin_group(
        self, test_client: TestClient, test_db
    ):
        test_db.add(
            SystemSettings(
                oidc_enabled=True,
                oidc_discovery_url="https://id.example.com/.well-known/openid-configuration",
                oidc_client_id="borg-ui",
                oidc_client_secret_encrypted=encrypt_secret("secret-value"),
                oidc_default_role="viewer",
                oidc_group_claim="groups",
                oidc_admin_groups="backup-admins",
            )
        )
        test_db.commit()

        create_test_oidc_exchange_grant(
            test_db,
            username="non-admin-claim-user",
            oidc_subject="subject-non-admin",
            email="non-admin@example.com",
            role="admin",
        )
        test_client.cookies.set("oidc_exchange_grant", "grant-123")

        response = test_client.post(
            "/api/auth/oidc/exchange", headers={"Origin": "http://testserver"}
        )

        assert response.status_code == 200
        user = (
            test_db.query(User).filter(User.username == "non-admin-claim-user").first()
        )
        assert user is not None
        assert user.role == "viewer"

    def test_oidc_logout_uses_stored_id_token_hint(
        self, test_client: TestClient, test_db, monkeypatch
    ):
        from app.core.oidc import OidcProviderConfiguration

        user = User(
            username="oidc-admin",
            password_hash=get_password_hash("irrelevant"),
            email="oidc-admin@example.com",
            role="admin",
            auth_source="oidc",
            oidc_last_id_token_encrypted=encrypt_secret("stored-id-token"),
            is_active=True,
        )
        test_db.add(user)
        test_db.add(
            SystemSettings(
                oidc_enabled=True,
                oidc_discovery_url="https://id.example.com/.well-known/openid-configuration",
                oidc_client_id="borg-ui",
                oidc_client_secret_encrypted=encrypt_secret("secret-value"),
            )
        )
        test_db.commit()
        test_db.refresh(user)

        async def fake_discover(request, settings_row, client_secret):
            return OidcProviderConfiguration(
                provider_name="Authentik",
                discovery_url="https://id.example.com/.well-known/openid-configuration",
                client_id="borg-ui",
                client_secret="secret-value",
                token_auth_method="client_secret_post",
                authorization_endpoint="https://id.example.com/auth",
                token_endpoint="https://id.example.com/token",
                userinfo_endpoint="https://id.example.com/userinfo",
                jwks_uri="https://id.example.com/jwks",
                issuer="https://id.example.com",
                scopes="openid profile email",
                redirect_uri="http://testserver/api/auth/oidc/callback",
                end_session_endpoint="https://id.example.com/logout",
                username_claim="preferred_username",
                email_claim="email",
                full_name_claim="name",
                group_claim=None,
                role_claim=None,
                admin_groups=[],
                all_repositories_role_claim=None,
                new_user_mode="viewer",
                new_user_template_username=None,
                default_role="viewer",
                default_all_repositories_role="viewer",
            )

        monkeypatch.setattr("app.api.auth.discover_oidc_configuration", fake_discover)

        token = create_access_token(data={"sub": user.username})
        response = test_client.post(
            "/api/auth/logout",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        assert "id_token_hint=stored-id-token" in response.json()["logout_url"]
        test_db.refresh(user)
        assert user.oidc_last_id_token_encrypted is None

    def test_local_logout_does_not_build_oidc_logout_url(
        self, test_client: TestClient, test_db, monkeypatch
    ):
        user = User(
            username="local-logout-user",
            password_hash=get_password_hash("password123"),
            email="local-logout@example.com",
            role="admin",
            is_active=True,
            auth_source="local",
            oidc_last_id_token_encrypted=encrypt_secret("stale-token"),
        )
        test_db.add(user)
        test_db.add(
            SystemSettings(
                oidc_enabled=True,
                oidc_discovery_url="https://id.example.com/.well-known/openid-configuration",
                oidc_client_id="borg-ui",
                oidc_client_secret_encrypted=encrypt_secret("secret-value"),
            )
        )
        test_db.commit()

        async def fail_discover(*args, **kwargs):
            raise AssertionError(
                "discover_oidc_configuration should not run for local logout"
            )

        monkeypatch.setattr("app.api.auth.discover_oidc_configuration", fail_discover)

        token = create_access_token(data={"sub": user.username})
        response = test_client.post(
            "/api/auth/logout",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        assert response.json()["logout_url"] is None

    def test_oidc_unlink_post_alias_clears_subject(
        self, test_client: TestClient, test_db
    ):
        user = User(
            username="linked-local-user",
            password_hash=get_password_hash("password123"),
            email="linked-local@example.com",
            role="admin",
            is_active=True,
            auth_source="oidc",
            oidc_subject="linked-subject",
            oidc_last_id_token_encrypted=encrypt_secret("stored-id-token"),
        )
        test_db.add(user)
        test_db.add(
            SystemSettings(
                oidc_enabled=True,
                oidc_discovery_url="https://id.example.com/.well-known/openid-configuration",
                oidc_client_id="borg-ui",
                oidc_client_secret_encrypted=encrypt_secret("secret-value"),
            )
        )
        test_db.commit()
        test_db.refresh(user)

        token = create_access_token(data={"sub": user.username})
        response = test_client.post(
            "/api/auth/oidc/unlink",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        test_db.refresh(user)
        assert user.auth_source == "local"
        assert user.oidc_subject is None
        assert user.oidc_last_id_token_encrypted is None
        test_db.refresh(user)
        assert user.oidc_last_id_token_encrypted is None

    def test_auth_events_endpoint_lists_recent_events(
        self, test_client: TestClient, admin_headers, test_db
    ):
        response = test_client.post(
            "/api/auth/login",
            data={"username": "admin", "password": "admin123"},
        )
        assert response.status_code == 200

        events_response = test_client.get(
            "/api/auth/events?limit=10", headers=admin_headers
        )

        assert events_response.status_code == 200
        events = events_response.json()
        assert isinstance(events, list)
        assert any(event["event_type"] == "local_login_succeeded" for event in events)


@pytest.mark.unit
class TestAuthRateLimiting:
    def test_local_login_rate_limit_returns_429(
        self, test_client: TestClient, test_db, monkeypatch
    ):
        monkeypatch.setattr("app.config.settings.auth_rate_limit_enabled", True)
        monkeypatch.setattr("app.config.settings.auth_rate_limit_max_attempts", 2)
        monkeypatch.setattr("app.config.settings.auth_rate_limit_window_seconds", 300)
        monkeypatch.setattr("app.config.settings.auth_rate_limit_lockout_seconds", 300)
        test_db.query(AuthRateLimitBucket).delete()
        test_db.commit()
        test_db.add(
            User(
                username="rate-limit-user",
                password_hash=get_password_hash("correct-password"),
                email="rate-limit@example.com",
                role="viewer",
                is_active=True,
            )
        )
        test_db.commit()

        response = test_client.post(
            "/api/auth/login",
            data={"username": "rate-limit-user", "password": "wrong-password"},
        )
        assert response.status_code == 401

        locked_response = test_client.post(
            "/api/auth/login",
            data={"username": "rate-limit-user", "password": "wrong-password"},
        )

        assert locked_response.status_code == 429
        assert (
            locked_response.json()["detail"]["key"]
            == "backend.errors.auth.tooManyRequests"
        )

    def test_successful_login_resets_local_rate_limit(
        self, test_client: TestClient, test_db, monkeypatch
    ):
        monkeypatch.setattr("app.config.settings.auth_rate_limit_enabled", True)
        monkeypatch.setattr("app.config.settings.auth_rate_limit_max_attempts", 2)
        monkeypatch.setattr("app.config.settings.auth_rate_limit_window_seconds", 300)
        monkeypatch.setattr("app.config.settings.auth_rate_limit_lockout_seconds", 300)
        test_db.query(AuthRateLimitBucket).delete()
        test_db.commit()
        test_db.add(
            User(
                username="rate-limit-reset-user",
                password_hash=get_password_hash("correct-password"),
                email="rate-limit-reset@example.com",
                role="viewer",
                is_active=True,
            )
        )
        test_db.commit()

        failed = test_client.post(
            "/api/auth/login",
            data={"username": "rate-limit-reset-user", "password": "wrong-password"},
        )
        assert failed.status_code == 401

        success = test_client.post(
            "/api/auth/login",
            data={
                "username": "rate-limit-reset-user",
                "password": "correct-password",
            },
        )
        assert success.status_code == 200

        another_failed = test_client.post(
            "/api/auth/login",
            data={"username": "rate-limit-reset-user", "password": "wrong-password"},
        )
        assert another_failed.status_code == 401
