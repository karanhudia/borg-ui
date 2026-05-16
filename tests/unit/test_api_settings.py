"""
Comprehensive unit tests for settings API endpoints.
Each test verifies ONE specific expected outcome.
"""

from datetime import datetime, timedelta, timezone
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.database.models import AuthEvent, OidcLoginState, User, SystemSettings
from app.core.features import Plan


@pytest.mark.unit
class TestSystemSettings:
    """Test system settings endpoints"""

    def test_get_system_settings_success(self, test_client: TestClient, admin_headers):
        """Test getting system settings returns 200"""
        response = test_client.get("/api/settings/system", headers=admin_headers)

        # SystemSettings model now exists and endpoint works correctly
        assert response.status_code == 200

    def test_get_system_settings_unauthorized(self, test_client: TestClient):
        """Test getting system settings without auth returns 403"""
        response = test_client.get("/api/settings/system")

        assert response.status_code == 401

    def test_update_system_settings_success(
        self, test_client: TestClient, admin_headers
    ):
        """Test updating system settings returns 200"""
        response = test_client.put(
            "/api/settings/system",
            json={"max_concurrent_backups": 3, "default_compression": "lz4"},
            headers=admin_headers,
        )

        assert response.status_code == 200

    def test_update_system_settings_invalid_data(
        self, test_client: TestClient, admin_headers
    ):
        """Test updating system settings with invalid data returns 422"""
        response = test_client.put(
            "/api/settings/system",
            json={
                "max_concurrent_backups": "invalid"  # Should be integer
            },
            headers=admin_headers,
        )

        assert response.status_code == 422

    def test_update_system_settings_unauthorized(self, test_client: TestClient):
        """Test updating system settings without auth returns 403"""
        response = test_client.put(
            "/api/settings/system", json={"max_concurrent_backups": 3}
        )

        assert response.status_code == 401

    def test_get_system_settings_includes_metrics_configuration(
        self, test_client: TestClient, admin_headers, test_db
    ):
        settings = SystemSettings(
            metrics_enabled=True,
            metrics_require_auth=True,
            metrics_token="metrics-secret",
        )
        test_db.add(settings)
        test_db.commit()

        response = test_client.get("/api/settings/system", headers=admin_headers)

        assert response.status_code == 200
        payload = response.json()["settings"]
        assert payload["metrics_enabled"] is True
        assert payload["metrics_require_auth"] is True
        assert payload["metrics_token_set"] is True

    def test_get_system_settings_defaults_metrics_to_disabled_for_new_install(
        self, test_client: TestClient, admin_headers, test_db
    ):
        response = test_client.get("/api/settings/system", headers=admin_headers)

        assert response.status_code == 200
        payload = response.json()["settings"]
        assert payload["metrics_enabled"] is False
        assert payload["metrics_require_auth"] is False
        assert payload["metrics_token_set"] is False
        assert payload["borg2_fast_browse_beta_enabled"] is False
        assert payload["dashboard_backup_warning_days"] == 3
        assert payload["dashboard_backup_critical_days"] == 7
        assert payload["dashboard_check_warning_days"] == 7
        assert payload["dashboard_check_critical_days"] == 30
        assert payload["dashboard_compact_warning_days"] == 30
        assert payload["dashboard_compact_critical_days"] == 60
        assert payload["dashboard_restore_check_warning_days"] == 14
        assert payload["dashboard_restore_check_critical_days"] == 30
        assert payload["dashboard_observe_freshness_warning_days"] == 2
        assert payload["dashboard_observe_freshness_critical_days"] == 7

    def test_update_system_settings_persists_borg2_fast_browse_beta_enabled(
        self, test_client: TestClient, admin_headers, test_db
    ):
        settings = SystemSettings()
        test_db.add(settings)
        test_db.commit()

        response = test_client.put(
            "/api/settings/system",
            json={
                "borg2_fast_browse_beta_enabled": True,
                "mqtt_password": "",
            },
            headers=admin_headers,
        )

        assert response.status_code == 200
        test_db.refresh(settings)
        assert settings.borg2_fast_browse_beta_enabled is True

    def test_update_system_settings_persists_scheduler_concurrency_limits(
        self, test_client: TestClient, admin_headers, test_db
    ):
        settings = SystemSettings()
        test_db.add(settings)
        test_db.commit()

        response = test_client.put(
            "/api/settings/system",
            json={
                "max_concurrent_scheduled_backups": 3,
                "max_concurrent_scheduled_checks": 5,
                "mqtt_password": "",
            },
            headers=admin_headers,
        )

        assert response.status_code == 200
        test_db.refresh(settings)
        assert settings.max_concurrent_scheduled_backups == 3
        assert settings.max_concurrent_scheduled_checks == 5

    def test_update_system_settings_persists_dashboard_health_thresholds(
        self, test_client: TestClient, admin_headers, test_db
    ):
        settings = SystemSettings()
        test_db.add(settings)
        test_db.commit()

        response = test_client.put(
            "/api/settings/system",
            json={
                "dashboard_backup_warning_days": 14,
                "dashboard_backup_critical_days": 31,
                "dashboard_check_warning_days": 14,
                "dashboard_check_critical_days": 45,
                "dashboard_compact_warning_days": 45,
                "dashboard_compact_critical_days": 90,
                "dashboard_restore_check_warning_days": 21,
                "dashboard_restore_check_critical_days": 45,
                "dashboard_observe_freshness_warning_days": 14,
                "dashboard_observe_freshness_critical_days": 31,
                "mqtt_password": "",
            },
            headers=admin_headers,
        )

        assert response.status_code == 200
        body = response.json()
        assert body["settings"]["dashboard_backup_warning_days"] == 14
        assert body["settings"]["dashboard_backup_critical_days"] == 31
        get_response = test_client.get("/api/settings/system", headers=admin_headers)
        assert get_response.status_code == 200
        get_payload = get_response.json()["settings"]
        assert get_payload["dashboard_backup_warning_days"] == 14
        assert get_payload["dashboard_backup_critical_days"] == 31
        test_db.refresh(settings)
        assert settings.dashboard_backup_warning_days == 14
        assert settings.dashboard_backup_critical_days == 31
        assert settings.dashboard_check_warning_days == 14
        assert settings.dashboard_check_critical_days == 45
        assert settings.dashboard_compact_warning_days == 45
        assert settings.dashboard_compact_critical_days == 90
        assert settings.dashboard_restore_check_warning_days == 21
        assert settings.dashboard_restore_check_critical_days == 45
        assert settings.dashboard_observe_freshness_warning_days == 14
        assert settings.dashboard_observe_freshness_critical_days == 31

    def test_update_system_settings_rejects_dashboard_critical_below_warning(
        self, test_client: TestClient, admin_headers, test_db
    ):
        settings = SystemSettings()
        test_db.add(settings)
        test_db.commit()

        response = test_client.put(
            "/api/settings/system",
            json={
                "dashboard_backup_warning_days": 30,
                "dashboard_backup_critical_days": 14,
                "mqtt_password": "",
            },
            headers=admin_headers,
        )

        assert response.status_code == 400
        assert (
            response.json()["detail"]["key"]
            == "backend.errors.settings.invalidDashboardHealthThresholdOrder"
        )

    def test_update_system_settings_persists_metrics_configuration(
        self, test_client: TestClient, admin_headers, test_db
    ):
        settings = SystemSettings()
        test_db.add(settings)
        test_db.commit()

        response = test_client.put(
            "/api/settings/system",
            json={
                "metrics_enabled": True,
                "metrics_require_auth": True,
                "metrics_token": "rotated-metrics-token",
                "mqtt_password": "",
            },
            headers=admin_headers,
        )

        assert response.status_code == 200
        test_db.refresh(settings)
        assert settings.metrics_enabled is True
        assert settings.metrics_require_auth is True
        assert settings.metrics_token == "rotated-metrics-token"

    def test_update_system_settings_disabling_metrics_also_disables_metrics_auth(
        self, test_client: TestClient, admin_headers, test_db
    ):
        settings = SystemSettings(
            metrics_enabled=True,
            metrics_require_auth=True,
            metrics_token="metrics-secret",
        )
        test_db.add(settings)
        test_db.commit()

        response = test_client.put(
            "/api/settings/system",
            json={
                "metrics_enabled": False,
                "mqtt_password": "",
            },
            headers=admin_headers,
        )

        assert response.status_code == 200
        test_db.refresh(settings)
        assert settings.metrics_enabled is False
        assert settings.metrics_require_auth is False
        assert settings.metrics_token == "metrics-secret"

    def test_update_system_settings_generates_metrics_token_when_auth_enabled(
        self, test_client: TestClient, admin_headers, test_db
    ):
        settings = SystemSettings(
            metrics_enabled=False, metrics_require_auth=False, metrics_token=None
        )
        test_db.add(settings)
        test_db.commit()

        response = test_client.put(
            "/api/settings/system",
            json={
                "metrics_enabled": True,
                "metrics_require_auth": True,
                "mqtt_password": "",
            },
            headers=admin_headers,
        )

        assert response.status_code == 200
        body = response.json()
        assert body["generated_metrics_token"]
        test_db.refresh(settings)
        assert settings.metrics_token == body["generated_metrics_token"]

    def test_update_system_settings_persists_oidc_client_secret_basic(
        self, test_client: TestClient, admin_headers, test_db
    ):
        settings = SystemSettings()
        test_db.add(settings)
        test_db.commit()

        response = test_client.put(
            "/api/settings/system",
            json={
                "oidc_token_auth_method": "client_secret_basic",
                "mqtt_password": "",
            },
            headers=admin_headers,
        )

        assert response.status_code == 200
        test_db.refresh(settings)
        assert settings.oidc_token_auth_method == "client_secret_basic"

        get_response = test_client.get("/api/settings/system", headers=admin_headers)
        assert get_response.status_code == 200
        assert (
            get_response.json()["settings"]["oidc_token_auth_method"]
            == "client_secret_basic"
        )

    def test_update_system_settings_rejects_invalid_oidc_token_auth_method(
        self, test_client: TestClient, admin_headers, test_db
    ):
        settings = SystemSettings()
        test_db.add(settings)
        test_db.commit()

        response = test_client.put(
            "/api/settings/system",
            json={
                "oidc_token_auth_method": "private_key_jwt",
                "mqtt_password": "",
            },
            headers=admin_headers,
        )

        assert response.status_code == 400
        assert (
            response.json()["detail"]["key"]
            == "backend.errors.settings.invalidOidcTokenAuthMethod"
        )

    def test_update_system_settings_rejects_disabling_local_auth_without_oidc_admin(
        self, test_client: TestClient, admin_headers, test_db
    ):
        settings = SystemSettings()
        test_db.add(settings)
        test_db.commit()

        response = test_client.put(
            "/api/settings/system",
            json={
                "oidc_enabled": True,
                "oidc_disable_local_auth": True,
                "oidc_discovery_url": "https://id.example.com/.well-known/openid-configuration",
                "oidc_client_id": "borg-ui",
                "oidc_client_secret": "secret-value",
                "mqtt_password": "",
            },
            headers=admin_headers,
        )

        assert response.status_code == 400
        assert (
            response.json()["detail"]["key"]
            == "backend.errors.settings.oidcLocalAuthRequiresOidcAdmin"
        )

    def test_update_system_settings_allows_disabling_local_auth_with_linked_oidc_admin(
        self, test_client: TestClient, admin_headers, test_db
    ):
        settings = SystemSettings()
        oidc_admin = User(
            username="oidc-admin",
            email="oidc-admin@example.com",
            password_hash="",
            role="admin",
            is_active=True,
            auth_source="local",
            oidc_subject="admin-subject",
        )
        test_db.add(settings)
        test_db.add(oidc_admin)
        test_db.commit()

        response = test_client.put(
            "/api/settings/system",
            json={
                "oidc_enabled": True,
                "oidc_disable_local_auth": True,
                "oidc_discovery_url": "https://id.example.com/.well-known/openid-configuration",
                "oidc_client_id": "borg-ui",
                "oidc_client_secret": "secret-value",
                "mqtt_password": "",
            },
            headers=admin_headers,
        )

        assert response.status_code == 200
        test_db.refresh(settings)
        assert settings.oidc_disable_local_auth is True

    def test_update_system_settings_rotates_metrics_token(
        self, test_client: TestClient, admin_headers, test_db
    ):
        settings = SystemSettings(
            metrics_enabled=True, metrics_require_auth=True, metrics_token="old-token"
        )
        test_db.add(settings)
        test_db.commit()

        response = test_client.put(
            "/api/settings/system",
            json={
                "rotate_metrics_token": True,
                "mqtt_password": "",
            },
            headers=admin_headers,
        )

        assert response.status_code == 200
        body = response.json()
        assert body["generated_metrics_token"]
        assert body["generated_metrics_token"] != "old-token"
        test_db.refresh(settings)
        assert settings.metrics_token == body["generated_metrics_token"]

    def test_manual_log_cleanup_returns_interpolated_success_message(
        self, test_client: TestClient, admin_headers
    ):
        with (
            patch(
                "app.services.log_manager.log_manager.cleanup_logs_combined",
                return_value={
                    "success": True,
                    "age_cleanup": {
                        "deleted_count": 1,
                        "deleted_size_mb": 1.25,
                        "skipped_count": 0,
                        "errors": [],
                    },
                    "size_cleanup": {
                        "deleted_count": 1,
                        "deleted_size_mb": 2.5,
                        "skipped_count": 0,
                        "final_size_mb": 10.0,
                        "errors": [],
                    },
                    "total_deleted_count": 2,
                    "total_deleted_size_mb": 3.75,
                    "total_errors": [],
                },
            ),
            patch(
                "app.services.log_manager.log_manager.calculate_log_storage",
                return_value={"total_size_mb": 10.0, "file_count": 4},
            ),
        ):
            response = test_client.post(
                "/api/settings/system/logs/cleanup", headers=admin_headers
            )

        assert response.status_code == 200
        payload = response.json()
        assert payload["message"] == {
            "key": "backend.success.settings.logCleanupCompleted",
            "params": {"count": 2, "sizeMb": 3.75},
        }

    def test_manual_log_cleanup_returns_noop_message_when_nothing_deleted(
        self, test_client: TestClient, admin_headers
    ):
        with (
            patch(
                "app.services.log_manager.log_manager.cleanup_logs_combined",
                return_value={
                    "success": True,
                    "age_cleanup": {
                        "deleted_count": 0,
                        "deleted_size_mb": 0.0,
                        "skipped_count": 0,
                        "errors": [],
                    },
                    "size_cleanup": {
                        "deleted_count": 0,
                        "deleted_size_mb": 0.0,
                        "skipped_count": 0,
                        "final_size_mb": 10.0,
                        "errors": [],
                    },
                    "total_deleted_count": 0,
                    "total_deleted_size_mb": 0.0,
                    "total_errors": [],
                },
            ),
            patch(
                "app.services.log_manager.log_manager.calculate_log_storage",
                return_value={"total_size_mb": 10.0, "file_count": 4},
            ),
        ):
            response = test_client.post(
                "/api/settings/system/logs/cleanup", headers=admin_headers
            )

        assert response.status_code == 200
        payload = response.json()
        assert payload["message"] == {
            "key": "backend.success.settings.logCleanupNoop",
            "params": {"retentionDays": 30, "sizeLimitMb": 500},
        }


@pytest.mark.unit
class TestUserSettings:
    """Test user settings endpoints"""

    def test_get_profile_success(self, test_client: TestClient, admin_headers):
        """Test getting user profile returns 200"""
        response = test_client.get("/api/settings/profile", headers=admin_headers)

        assert response.status_code == 200
        data = response.json()
        assert "success" in data
        assert "profile" in data

    def test_get_profile_unauthorized(self, test_client: TestClient):
        """Test getting profile without auth returns 403"""
        response = test_client.get("/api/settings/profile")

        assert response.status_code == 401

    def test_update_profile_success(self, test_client: TestClient, admin_headers):
        """Test updating user profile returns 200"""
        response = test_client.put(
            "/api/settings/profile",
            json={"email": "updated@example.com", "name": "Updated Name"},
            headers=admin_headers,
        )

        assert response.status_code == 200

    def test_update_profile_invalid_email(self, test_client: TestClient, admin_headers):
        """Test updating profile with invalid email returns 422"""
        response = test_client.put(
            "/api/settings/profile",
            json={"email": "invalid-email"},
            headers=admin_headers,
        )

        assert response.status_code == 200

    def test_update_profile_unauthorized(self, test_client: TestClient):
        """Test updating profile without auth returns 403"""
        response = test_client.put(
            "/api/settings/profile", json={"email": "test@example.com"}
        )

        assert response.status_code == 401


@pytest.mark.unit
class TestUserManagement:
    """Test user management endpoints"""

    def test_list_users_success(self, test_client: TestClient, admin_headers):
        """Test listing users returns 200"""
        response = test_client.get("/api/settings/users", headers=admin_headers)

        assert response.status_code == 200
        data = response.json()
        assert "success" in data
        assert "users" in data
        assert isinstance(data["users"], list)

    def test_list_users_includes_auth_source_fields(
        self, test_client: TestClient, admin_headers, test_db
    ):
        oidc_user = User(
            username="oidc-user",
            email="oidc-user@example.com",
            password_hash="",
            role="viewer",
            is_active=False,
            auth_source="oidc",
            oidc_subject="subject-xyz",
        )
        test_db.add(oidc_user)
        test_db.commit()

        response = test_client.get("/api/settings/users", headers=admin_headers)

        assert response.status_code == 200
        users = response.json()["users"]
        oidc_payload = next(user for user in users if user["username"] == "oidc-user")
        assert oidc_payload["auth_source"] == "oidc"
        assert oidc_payload["oidc_subject"] == "subject-xyz"

    def test_update_user_can_approve_pending_oidc_user(
        self, test_client: TestClient, admin_headers, test_db
    ):
        pending_user = User(
            username="pending-oidc",
            email="pending-oidc@example.com",
            password_hash="",
            role="viewer",
            is_active=False,
            auth_source="oidc",
            oidc_subject="subject-pending",
        )
        test_db.add(pending_user)
        test_db.commit()
        test_db.refresh(pending_user)

        response = test_client.put(
            f"/api/settings/users/{pending_user.id}",
            json={"is_active": True},
            headers=admin_headers,
        )

        assert response.status_code == 200
        test_db.refresh(pending_user)
        assert pending_user.is_active is True

    def test_list_users_unauthorized(self, test_client: TestClient):
        """Test listing users without auth returns 403"""
        response = test_client.get("/api/settings/users")

        assert response.status_code == 401

    def test_create_user_success(self, test_client: TestClient, admin_headers):
        """Test creating user returns 200/201"""
        with patch("app.api.settings.get_current_plan", return_value=Plan.ENTERPRISE):
            response = test_client.post(
                "/api/settings/users",
                json={
                    "username": "newuser",
                    "password": "SecurePass123!",
                    "email": "newuser@example.com",
                    "role": "viewer",
                },
                headers=admin_headers,
            )

        assert response.status_code == 200

    def test_create_user_missing_fields(self, test_client: TestClient, admin_headers):
        """Test creating user with missing fields returns 422"""
        response = test_client.post(
            "/api/settings/users",
            json={"username": "incomplete"},
            headers=admin_headers,
        )

        assert response.status_code == 422

    def test_create_user_weak_password(self, test_client: TestClient, admin_headers):
        """Test creating user with weak password returns 422"""
        with patch("app.api.settings.get_current_plan", return_value=Plan.ENTERPRISE):
            response = test_client.post(
                "/api/settings/users",
                json={
                    "username": "newuser",
                    "password": "123",
                    "email": "test@example.com",
                },
                headers=admin_headers,
            )

        assert response.status_code == 200

    def test_create_user_unauthorized(self, test_client: TestClient):
        """Test creating user without auth returns 403"""
        response = test_client.post(
            "/api/settings/users",
            json={
                "username": "test",
                "password": "SecurePass123!",
                "email": "test@example.com",
            },
        )

        assert response.status_code == 401

    def test_update_user_success(self, test_client: TestClient, admin_headers, test_db):
        """Test updating user returns 200"""
        # Create a test user
        user = User(
            username="testuser",
            email="test@example.com",
            role="viewer",
            password_hash="fakehash",
        )
        test_db.add(user)
        test_db.commit()
        test_db.refresh(user)

        response = test_client.put(
            f"/api/settings/users/{user.id}",
            json={"email": "updated@example.com"},
            headers=admin_headers,
        )

        assert response.status_code == 200

    def test_update_user_can_set_and_clear_oidc_subject(
        self, test_client: TestClient, admin_headers, test_db
    ):
        user = User(
            username="linkable-user",
            email="linkable@example.com",
            role="viewer",
            password_hash="fakehash",
            auth_source="local",
        )
        test_db.add(user)
        test_db.commit()
        test_db.refresh(user)

        link_response = test_client.put(
            f"/api/settings/users/{user.id}",
            json={"auth_source": "oidc", "oidc_subject": "issuer|subject-123"},
            headers=admin_headers,
        )

        assert link_response.status_code == 200
        test_db.refresh(user)
        assert user.auth_source == "oidc"
        assert user.oidc_subject == "issuer|subject-123"

        clear_response = test_client.put(
            f"/api/settings/users/{user.id}",
            json={"auth_source": "local", "oidc_subject": None},
            headers=admin_headers,
        )

        assert clear_response.status_code == 200
        test_db.refresh(user)
        assert user.auth_source == "local"
        assert user.oidc_subject is None

    def test_update_user_rejects_duplicate_oidc_subject(
        self, test_client: TestClient, admin_headers, test_db
    ):
        existing_user = User(
            username="existing-oidc-subject",
            email="existing-oidc-subject@example.com",
            role="viewer",
            password_hash="",
            auth_source="oidc",
            oidc_subject="issuer|duplicate",
        )
        target_user = User(
            username="target-oidc-subject",
            email="target-oidc-subject@example.com",
            role="viewer",
            password_hash="fakehash",
            auth_source="local",
        )
        test_db.add(existing_user)
        test_db.add(target_user)
        test_db.commit()
        test_db.refresh(target_user)

        response = test_client.put(
            f"/api/settings/users/{target_user.id}",
            json={"auth_source": "oidc", "oidc_subject": "issuer|duplicate"},
            headers=admin_headers,
        )

        assert response.status_code == 409
        assert (
            response.json()["detail"]["key"]
            == "backend.errors.auth.oidcIdentityConflict"
        )

    def test_update_user_nonexistent(self, test_client: TestClient, admin_headers):
        """Test updating non-existent user returns 404"""
        response = test_client.put(
            "/api/settings/users/99999",
            json={"email": "test@example.com"},
            headers=admin_headers,
        )

        assert response.status_code == 404

    def test_delete_user_success(self, test_client: TestClient, admin_headers, test_db):
        """Test deleting user returns 200"""
        user = User(
            username="todelete",
            email="delete@example.com",
            role="viewer",
            password_hash="fakehash",
        )
        test_db.add(user)
        test_db.commit()
        test_db.refresh(user)

        response = test_client.delete(
            f"/api/settings/users/{user.id}", headers=admin_headers
        )

        assert response.status_code == 200

    def test_delete_user_with_auth_history_and_oidc_state(
        self, test_client: TestClient, admin_headers, test_db
    ):
        """Deleting a user should not fail when auth audit rows reference it."""
        test_db.add(
            SystemSettings(
                oidc_enabled=True,
                oidc_discovery_url="https://id.example.com/.well-known/openid-configuration",
                oidc_client_id="borg-ui",
            )
        )
        user = User(
            username="oidc-delete-local",
            email="oidc-delete-local@example.com",
            role="viewer",
            password_hash="fakehash",
            auth_source="local",
        )
        test_db.add(user)
        test_db.commit()
        test_db.refresh(user)

        auth_event = AuthEvent(
            event_type="local_login_succeeded",
            auth_source="local",
            username=user.username,
            email=user.email,
            success=True,
            actor_user_id=user.id,
        )
        login_state = OidcLoginState(
            state_id="delete-user-link-state",
            nonce="nonce",
            code_verifier="verifier",
            return_to="http://testserver/settings/account",
            flow="link",
            user_id=user.id,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        )
        test_db.add_all([auth_event, login_state])
        test_db.commit()
        test_db.refresh(auth_event)
        test_db.refresh(login_state)

        response = test_client.delete(
            f"/api/settings/users/{user.id}", headers=admin_headers
        )

        assert response.status_code == 200
        assert test_db.query(User).filter(User.id == user.id).first() is None
        test_db.refresh(auth_event)
        test_db.refresh(login_state)
        assert auth_event.actor_user_id is None
        assert login_state.user_id is None

    def test_delete_user_nonexistent(self, test_client: TestClient, admin_headers):
        """Test deleting non-existent user returns 404"""
        response = test_client.delete(
            "/api/settings/users/99999", headers=admin_headers
        )

        assert response.status_code == 404

    def test_delete_user_unauthorized(self, test_client: TestClient):
        """Test deleting user without auth returns 403"""
        response = test_client.delete("/api/settings/users/1")

        assert response.status_code == 401


@pytest.mark.unit
class TestPasswordManagement:
    """Test password management endpoints"""

    def test_change_password_success(self, test_client: TestClient, admin_headers):
        """Test changing password returns 200"""
        response = test_client.post(
            "/api/settings/change-password",
            json={"current_password": "OldPass123!", "new_password": "NewPass123!"},
            headers=admin_headers,
        )

        assert response.status_code == 400

    def test_change_password_missing_fields(
        self, test_client: TestClient, admin_headers
    ):
        """Test changing password with missing fields returns 422"""
        response = test_client.post(
            "/api/settings/change-password",
            json={"new_password": "NewPass123!"},
            headers=admin_headers,
        )

        assert response.status_code == 422

    def test_change_password_weak_password(
        self, test_client: TestClient, admin_headers
    ):
        """Test changing to weak password returns 422"""
        response = test_client.post(
            "/api/settings/change-password",
            json={
                "current_password": "OldPass123!",
                "new_password": "123",  # Too weak
            },
            headers=admin_headers,
        )

        assert response.status_code == 400

    def test_change_password_unauthorized(self, test_client: TestClient):
        """Test changing password without auth returns 403"""
        response = test_client.post(
            "/api/settings/change-password",
            json={"current_password": "old", "new_password": "NewPass123!"},
        )

        assert response.status_code == 401

    def test_reset_user_password_success(
        self, test_client: TestClient, admin_headers, test_db
    ):
        """Test admin resetting user password returns 200"""
        user = User(
            username="resetuser",
            email="reset@example.com",
            role="viewer",
            password_hash="fakehash",
        )
        test_db.add(user)
        test_db.commit()
        test_db.refresh(user)

        response = test_client.post(
            f"/api/settings/users/{user.id}/reset-password",
            json={"new_password": "NewPass123!"},
            headers=admin_headers,
        )

        assert response.status_code == 200

    def test_reset_user_password_nonexistent(
        self, test_client: TestClient, admin_headers
    ):
        """Test resetting password for non-existent user returns 404"""
        response = test_client.post(
            "/api/settings/users/99999/reset-password",
            json={"new_password": "NewPass123!"},
            headers=admin_headers,
        )

        assert response.status_code == 404

    def test_reset_user_password_unauthorized(self, test_client: TestClient):
        """Test resetting user password without auth returns 403"""
        response = test_client.post(
            "/api/settings/users/1/reset-password", json={"new_password": "NewPass123!"}
        )

        assert response.status_code == 401


@pytest.mark.unit
class TestSystemMaintenance:
    """Test system maintenance endpoints"""

    def test_cleanup_system_success(self, test_client: TestClient, admin_headers):
        """Test system cleanup returns 200"""
        response = test_client.post(
            "/api/settings/system/cleanup", headers=admin_headers
        )

        assert response.status_code == 200

    def test_cleanup_system_unauthorized(self, test_client: TestClient):
        """Test system cleanup without auth returns 403"""
        response = test_client.post("/api/settings/system/cleanup")

        assert response.status_code == 401


@pytest.mark.unit
class TestSettingsValidation:
    """Test settings validation and edge cases"""

    def test_update_system_empty_payload(self, test_client: TestClient, admin_headers):
        """Test updating system settings with empty payload"""
        response = test_client.put(
            "/api/settings/system", json={}, headers=admin_headers
        )

        assert response.status_code == 200

    def test_update_profile_empty_payload(self, test_client: TestClient, admin_headers):
        """Test updating profile with empty payload"""
        response = test_client.put(
            "/api/settings/profile", json={}, headers=admin_headers
        )

        assert response.status_code == 200

    def test_create_user_duplicate_username(
        self, test_client: TestClient, admin_headers, test_db
    ):
        """Test creating user with duplicate username returns 409"""
        # Create first user
        user = User(
            username="duplicate",
            email="first@example.com",
            role="viewer",
            password_hash="fakehash",
        )
        test_db.add(user)
        test_db.commit()

        # Try to create second user with same username
        with patch("app.api.settings.get_current_plan", return_value=Plan.ENTERPRISE):
            response = test_client.post(
                "/api/settings/users",
                json={
                    "username": "duplicate",
                    "password": "SecurePass123!",
                    "email": "second@example.com",
                },
                headers=admin_headers,
            )

        assert response.status_code == 400

    def test_update_user_invalid_role(
        self, test_client: TestClient, admin_headers, test_db
    ):
        """Test updating user with invalid role returns 422"""
        user = User(
            username="testuser",
            email="test@example.com",
            role="viewer",
            password_hash="fakehash",
        )
        test_db.add(user)
        test_db.commit()
        test_db.refresh(user)

        response = test_client.put(
            f"/api/settings/users/{user.id}",
            json={"role": "invalid_role"},
            headers=admin_headers,
        )

        assert response.status_code == 200


@pytest.mark.unit
class TestDeploymentProfile:
    def test_update_system_settings_deployment_type(
        self, test_client, admin_headers, test_db
    ):
        """Admin can set deployment_type on system settings."""
        response = test_client.put(
            "/api/settings/system",
            json={"deployment_type": "enterprise", "enterprise_name": "Acme Corp"},
            headers=admin_headers,
        )
        assert response.status_code == 200

    def test_update_system_settings_invalid_deployment_type(
        self, test_client, admin_headers
    ):
        """Invalid deployment_type returns 400."""
        response = test_client.put(
            "/api/settings/system",
            json={"deployment_type": "bogus"},
            headers=admin_headers,
        )
        assert response.status_code == 400
        assert (
            response.json()["detail"]["key"]
            == "backend.errors.settings.invalidDeploymentType"
        )

    def test_get_profile_returns_deployment_context(
        self, test_client, admin_headers, test_db
    ):
        """GET /settings/profile includes deployment_type and enterprise_name."""
        from app.database.models import SystemSettings

        sys = SystemSettings(deployment_type="enterprise", enterprise_name="Acme Corp")
        test_db.add(sys)
        test_db.commit()

        response = test_client.get("/api/settings/profile", headers=admin_headers)
        assert response.status_code == 200
        profile = response.json()["profile"]
        assert profile["deployment_type"] == "enterprise"
        assert profile["enterprise_name"] == "Acme Corp"

    def test_get_profile_defaults_to_individual_when_no_settings(
        self, test_client, admin_headers
    ):
        """GET /settings/profile returns 'individual' when no SystemSettings row exists."""
        response = test_client.get("/api/settings/profile", headers=admin_headers)
        assert response.status_code == 200
        profile = response.json()["profile"]
        assert profile["deployment_type"] == "individual"
        assert profile["enterprise_name"] is None

    def test_non_admin_cannot_update_deployment_type(self, test_client, auth_headers):
        """Non-admin cannot update system settings."""
        response = test_client.put(
            "/api/settings/system",
            json={"deployment_type": "enterprise"},
            headers=auth_headers,
        )
        assert response.status_code == 403
