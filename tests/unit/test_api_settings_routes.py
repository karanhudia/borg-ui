from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi.testclient import TestClient

from app.api import settings as settings_api
from app.database.models import LicensingState, Repository, SystemSettings, User


@pytest.mark.unit
class TestSystemSettingsContracts:
    def test_get_effective_timeout_prefers_saved_value_over_env(self):
        value, source = settings_api.get_effective_timeout(600, 120, 300)

        assert value == 600
        assert source == "saved"

    def test_get_effective_timeout_uses_env_when_db_matches_default(self):
        value, source = settings_api.get_effective_timeout(300, 450, 300)

        assert value == 450
        assert source == "env"

    def test_get_effective_timeout_falls_back_to_default(self):
        value, source = settings_api.get_effective_timeout(None, 300, 300)

        assert value == 300
        assert source is None

    def test_get_system_settings_creates_defaults_and_reports_timeout_sources(
        self, test_client: TestClient, admin_headers, test_db
    ):
        response = test_client.get("/api/settings/system", headers=admin_headers)

        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        settings = body["settings"]
        assert settings["max_concurrent_backups"] == 2
        assert settings["max_concurrent_scheduled_backups"] == 2
        assert settings["max_concurrent_scheduled_checks"] == 4
        assert settings["log_retention_days"] == 30
        assert settings["timeout_sources"]["backup_timeout"] in (None, "env")
        assert settings["app_version"] == "2.1.0"
        assert test_db.query(SystemSettings).count() == 1

    def test_get_system_settings_falls_back_when_log_storage_lookup_fails(
        self, test_client: TestClient, admin_headers
    ):
        fake_log_manager = Mock()
        fake_log_manager.calculate_log_storage.side_effect = RuntimeError("boom")

        with patch("app.services.log_manager.log_manager", fake_log_manager):
            response = test_client.get("/api/settings/system", headers=admin_headers)

        assert response.status_code == 200
        log_storage = response.json()["log_storage"]
        assert log_storage["total_size_mb"] == 0
        assert log_storage["file_count"] == 0
        assert log_storage["files_by_type"] == {}

    def test_update_system_settings_rejects_invalid_log_save_policy(
        self, test_client: TestClient, admin_headers
    ):
        response = test_client.put(
            "/api/settings/system",
            json={"log_save_policy": "invalid-policy"},
            headers=admin_headers,
        )

        assert response.status_code == 400
        assert (
            response.json()["detail"]["key"]
            == "backend.errors.settings.invalidLogSavePolicy"
        )

    def test_update_system_settings_rejects_too_small_log_limit(
        self, test_client: TestClient, admin_headers
    ):
        response = test_client.put(
            "/api/settings/system",
            json={"log_max_total_size_mb": 5},
            headers=admin_headers,
        )

        assert response.status_code == 400
        assert (
            response.json()["detail"]["key"]
            == "backend.errors.settings.logSizeTooSmall"
        )

    def test_update_system_settings_rejects_negative_scheduler_limit(
        self, test_client: TestClient, admin_headers
    ):
        response = test_client.put(
            "/api/settings/system",
            json={"max_concurrent_scheduled_checks": -1},
            headers=admin_headers,
        )

        assert response.status_code == 400
        assert (
            response.json()["detail"]["key"]
            == "backend.errors.settings.invalidConcurrencyLimit"
        )

    def test_update_system_settings_returns_warning_when_new_log_limit_is_below_current_usage(
        self, test_client: TestClient, admin_headers
    ):
        fake_log_manager = Mock()
        fake_log_manager.calculate_log_storage.return_value = {"total_size_mb": 250}

        with (
            patch("app.services.log_manager.log_manager", fake_log_manager),
            patch("app.services.mqtt_service.mqtt_service.configure"),
            patch(
                "app.services.mqtt_service.build_mqtt_runtime_config",
                return_value={"enabled": False},
            ),
        ):
            response = test_client.put(
                "/api/settings/system",
                json={"log_max_total_size_mb": 100, "mqtt_password": ""},
                headers=admin_headers,
            )

        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert len(body["warnings"]) == 1
        assert "exceeds new limit" in body["warnings"][0]


@pytest.mark.unit
class TestSettingsUserContracts:
    def test_create_user_rejects_duplicate_email(
        self, test_client: TestClient, admin_headers, test_db
    ):
        test_db.add(SystemSettings())
        state = test_db.query(LicensingState).first()
        if state is None:
            state = LicensingState(instance_id="test-instance-settings-users")
            test_db.add(state)
        state.plan = "pro"
        state.status = "active"
        state.is_trial = False
        existing = User(
            username="existing",
            email="taken@example.com",
            role="viewer",
            password_hash="hash",
        )
        test_db.add(existing)
        test_db.commit()

        response = test_client.post(
            "/api/settings/users",
            json={
                "username": "new-user",
                "password": "SecurePass123!",
                "email": "taken@example.com",
                "role": "viewer",
            },
            headers=admin_headers,
        )

        assert response.status_code == 400
        assert (
            response.json()["detail"]["key"]
            == "backend.errors.settings.emailAlreadyExists"
        )

    def test_update_user_role_normalizes_repository_scope(
        self, test_client: TestClient, admin_headers, test_db
    ):
        user = User(
            username="scoped-user",
            email="scoped@example.com",
            role="viewer",
            all_repositories_role="operator",
            password_hash="hash",
        )
        test_db.add(user)
        test_db.commit()
        test_db.refresh(user)

        response = test_client.put(
            f"/api/settings/users/{user.id}",
            json={"role": "viewer"},
            headers=admin_headers,
        )

        assert response.status_code == 200
        test_db.refresh(user)
        assert user.role == "viewer"
        assert user.all_repositories_role == "viewer"

    def test_delete_user_rejects_deleting_self(
        self, test_client: TestClient, admin_headers, admin_user, test_db
    ):
        test_db.add(
            User(
                username="other-admin",
                email="other-admin@example.com",
                role="admin",
                password_hash="hash",
            )
        )
        test_db.commit()

        response = test_client.delete(
            f"/api/settings/users/{admin_user.id}", headers=admin_headers
        )

        assert response.status_code == 400
        assert (
            response.json()["detail"]["key"]
            == "backend.errors.settings.cannotDeleteOwnAccount"
        )

    def test_change_password_rejects_wrong_current_password(
        self, test_client: TestClient, admin_headers
    ):
        response = test_client.post(
            "/api/settings/change-password",
            json={"current_password": "wrong-password", "new_password": "NewPass123!"},
            headers=admin_headers,
        )

        assert response.status_code == 400
        assert (
            response.json()["detail"]["key"]
            == "backend.errors.auth.currentPasswordIncorrect"
        )

    def test_get_profile_includes_deployment_metadata(
        self, test_client: TestClient, admin_headers, test_db
    ):
        settings = SystemSettings(
            deployment_type="enterprise", enterprise_name="Acme Inc"
        )
        test_db.add(settings)
        test_db.commit()

        response = test_client.get("/api/settings/profile", headers=admin_headers)

        assert response.status_code == 200
        profile = response.json()["profile"]
        assert profile["deployment_type"] == "enterprise"
        assert profile["enterprise_name"] == "Acme Inc"

    def test_get_preferences_returns_user_analytics_flags(
        self, test_client: TestClient, admin_headers, admin_user
    ):
        admin_user.analytics_enabled = False
        admin_user.analytics_consent_given = True

        response = test_client.get("/api/settings/preferences", headers=admin_headers)

        assert response.status_code == 200
        assert response.json() == {
            "success": True,
            "preferences": {
                "analytics_enabled": False,
                "analytics_consent_given": True,
            },
        }

    def test_update_preferences_persists_analytics_flags(
        self, test_client: TestClient, admin_headers, admin_user, test_db
    ):
        response = test_client.put(
            "/api/settings/preferences",
            json={"analytics_enabled": False, "analytics_consent_given": True},
            headers=admin_headers,
        )

        assert response.status_code == 200
        test_db.refresh(admin_user)
        assert admin_user.analytics_enabled is False
        assert admin_user.analytics_consent_given is True
        assert (
            response.json()["message"] == "backend.success.settings.preferencesUpdated"
        )


@pytest.mark.unit
class TestCacheSettingsContracts:
    def test_clear_cache_rejects_missing_repository(
        self, test_client: TestClient, admin_headers
    ):
        response = test_client.post(
            "/api/settings/cache/clear?repository_id=99999", headers=admin_headers
        )

        assert response.status_code == 404
        assert (
            response.json()["detail"]["key"] == "backend.errors.repo.repositoryNotFound"
        )

    def test_clear_cache_for_repository_returns_cleared_count(
        self, test_client: TestClient, admin_headers, test_db
    ):
        repository = Repository(
            name="Repo", path="/repos/main", encryption="none", repository_type="local"
        )
        test_db.add(repository)
        test_db.commit()
        test_db.refresh(repository)

        with patch(
            "app.api.settings.archive_cache.clear_repository",
            new=AsyncMock(return_value=3),
        ) as mock_clear:
            response = test_client.post(
                f"/api/settings/cache/clear?repository_id={repository.id}",
                headers=admin_headers,
            )

        assert response.status_code == 200
        assert response.json()["cleared_count"] == 3
        mock_clear.assert_awaited_once_with(repository.id)

    def test_update_cache_settings_requires_at_least_one_value(
        self, test_client: TestClient, admin_headers
    ):
        response = test_client.put(
            "/api/settings/cache/settings", headers=admin_headers
        )

        assert response.status_code == 400
        assert (
            response.json()["detail"]["key"]
            == "backend.errors.settings.atLeastOneSettingRequired"
        )

    def test_update_cache_settings_reconfigures_backend(
        self, test_client: TestClient, admin_headers, test_db
    ):
        with patch(
            "app.api.settings.archive_cache.reconfigure",
            return_value={"success": True, "backend": "in-memory"},
        ) as mock_reconfigure:
            response = test_client.put(
                "/api/settings/cache/settings?cache_ttl_minutes=90&cache_max_size_mb=256&redis_url=disabled",
                headers=admin_headers,
            )

        assert response.status_code == 200
        body = response.json()
        assert body["message"] == "backend.success.settings.cacheSettingsUpdated"
        assert body["backend"] == "in-memory"
        assert body["cache_ttl_minutes"] == 90
        assert body["cache_max_size_mb"] == 256
        mock_reconfigure.assert_called_once_with(
            redis_url="disabled", cache_max_size_mb=256
        )
        settings = test_db.query(SystemSettings).first()
        assert settings.cache_ttl_minutes == 90
        assert settings.cache_max_size_mb == 256
        assert settings.redis_url == "disabled"

    def test_get_log_storage_stats_reports_usage_percent(
        self, test_client: TestClient, admin_headers, test_db
    ):
        test_db.add(SystemSettings(log_max_total_size_mb=200))
        test_db.commit()

        fake_log_manager = Mock()
        fake_log_manager.calculate_log_storage.return_value = {
            "total_size_bytes": 50 * 1024 * 1024,
            "total_size_mb": 50,
            "file_count": 4,
            "oldest_log_date": None,
            "newest_log_date": None,
            "files_by_type": {"backup": 2, "restore": 2},
        }

        with patch("app.services.log_manager.log_manager", fake_log_manager):
            response = test_client.get(
                "/api/settings/system/logs/storage", headers=admin_headers
            )

        assert response.status_code == 200
        log_storage = response.json()["storage"]
        assert log_storage["usage_percent"] == 25
        assert log_storage["file_count"] == 4
        assert log_storage["files_by_type"] == {"backup": 2, "restore": 2}
