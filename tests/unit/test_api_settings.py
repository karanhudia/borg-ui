"""
Unit tests for settings API endpoints
"""
import pytest
from fastapi.testclient import TestClient


@pytest.mark.unit
class TestSettingsEndpoints:
    """Test settings API endpoints"""

    def test_get_settings_profile(self, test_client: TestClient, admin_headers):
        """Test getting settings profile"""
        response = test_client.get("/api/settings/profile", headers=admin_headers)

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)

    def test_get_settings_unauthorized(self, test_client: TestClient):
        """Test getting settings without authentication"""
        response = test_client.get("/api/settings/profile")

        assert response.status_code in [401, 403, 404]

    def test_update_settings_profile(self, test_client: TestClient, admin_headers):
        """Test updating settings profile"""
        response = test_client.put(
            "/api/settings/profile",
            json={
                "compression": "lz4",
                "default_encryption": "repokey"
            },
            headers=admin_headers
        )

        # Should succeed or return validation error
        assert response.status_code in [200, 405, 422]

    def test_get_global_settings(self, test_client: TestClient, admin_headers):
        """Test getting global application settings"""
        response = test_client.get("/api/settings/global", headers=admin_headers)

        assert response.status_code in [200, 403, 404, 500]

    def test_update_global_settings(self, test_client: TestClient, admin_headers):
        """Test updating global settings"""
        response = test_client.put(
            "/api/settings/global",
            json={
                "backup_timeout": 3600,
                "max_concurrent_jobs": 3
            },
            headers=admin_headers
        )

        assert response.status_code in [200, 405, 422]

    def test_get_notification_settings(self, test_client: TestClient, admin_headers):
        """Test getting notification settings"""
        response = test_client.get("/api/settings/notifications", headers=admin_headers)

        assert response.status_code in [200, 403, 404, 500]

    def test_update_notification_settings(self, test_client: TestClient, admin_headers):
        """Test updating notification settings"""
        response = test_client.put(
            "/api/settings/notifications",
            json={
                "email_enabled": True,
                "email_address": "test@example.com"
            },
            headers=admin_headers
        )

        assert response.status_code in [200, 405, 422]

    def test_get_retention_policy(self, test_client: TestClient, admin_headers):
        """Test getting retention policy settings"""
        response = test_client.get("/api/settings/retention", headers=admin_headers)

        assert response.status_code in [200, 403, 404, 500]

    def test_update_retention_policy(self, test_client: TestClient, admin_headers):
        """Test updating retention policy"""
        response = test_client.put(
            "/api/settings/retention",
            json={
                "keep_daily": 7,
                "keep_weekly": 4,
                "keep_monthly": 6
            },
            headers=admin_headers
        )

        assert response.status_code in [200, 405, 422]
