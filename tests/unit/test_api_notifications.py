"""
Unit tests for notification settings API endpoints
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch

from app.database.models import NotificationSettings, Repository


@pytest.mark.unit
class TestNotificationSettingsAPI:
    """Test notification settings endpoints"""

    def test_list_notification_settings_empty(
        self, test_client: TestClient, admin_headers
    ):
        response = test_client.get("/api/notifications", headers=admin_headers)

        assert response.status_code == 200
        assert response.json() == []

    def test_create_notification_setting_all_repositories(
        self,
        test_client: TestClient,
        admin_headers,
        test_db,
    ):
        response = test_client.post(
            "/api/notifications",
            json={
                "name": "Slack Alerts",
                "service_url": "slack://token/",
                "enabled": True,
            },
            headers=admin_headers,
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Slack Alerts"
        assert data["enabled"] is True
        assert data["monitor_all_repositories"] is True
        assert data["repositories"] == []

        setting = (
            test_db.query(NotificationSettings)
            .filter(NotificationSettings.name == "Slack Alerts")
            .first()
        )
        assert setting is not None

    def test_create_notification_setting_with_repository_filter(
        self,
        test_client: TestClient,
        admin_headers,
        test_db,
    ):
        repo = Repository(
            name="Repo A",
            path="/tmp/repo-a",
            encryption="none",
            repository_type="local",
        )
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        response = test_client.post(
            "/api/notifications",
            json={
                "name": "Filtered Alerts",
                "service_url": "json://example",
                "monitor_all_repositories": False,
                "repository_ids": [repo.id],
            },
            headers=admin_headers,
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Filtered Alerts"
        assert len(data["repositories"]) == 1
        assert data["repositories"][0]["id"] == repo.id

    def test_get_notification_setting_not_found(
        self, test_client: TestClient, admin_headers
    ):
        response = test_client.get("/api/notifications/999999", headers=admin_headers)

        assert response.status_code == 404
        assert (
            response.json()["detail"]["key"]
            == "backend.errors.notifications.settingNotFound"
        )

    def test_get_notification_setting_success(
        self, test_client: TestClient, admin_headers, test_db
    ):
        setting = NotificationSettings(name="Read Me", service_url="slack://token/")
        test_db.add(setting)
        test_db.commit()
        test_db.refresh(setting)

        response = test_client.get(
            f"/api/notifications/{setting.id}", headers=admin_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == setting.id
        assert data["name"] == "Read Me"

    def test_update_notification_setting_not_found(
        self, test_client: TestClient, admin_headers
    ):
        response = test_client.put(
            "/api/notifications/999999",
            json={"name": "missing"},
            headers=admin_headers,
        )

        assert response.status_code == 404
        assert (
            response.json()["detail"]["key"]
            == "backend.errors.notifications.settingNotFound"
        )

    def test_update_notification_setting_clears_repositories_when_monitor_all(
        self, test_client: TestClient, admin_headers, test_db
    ):
        repo = Repository(
            name="Repo B",
            path="/tmp/repo-b",
            encryption="none",
            repository_type="local",
        )
        setting = NotificationSettings(
            name="Scoped Alerts",
            service_url="slack://token/",
            monitor_all_repositories=False,
        )
        test_db.add_all([repo, setting])
        test_db.commit()
        test_db.refresh(repo)
        test_db.refresh(setting)
        setting.repositories = [repo]
        test_db.commit()

        response = test_client.put(
            f"/api/notifications/{setting.id}",
            json={
                "monitor_all_repositories": True,
                "repository_ids": [repo.id],
            },
            headers=admin_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["monitor_all_repositories"] is True
        assert data["repositories"] == []

    def test_delete_notification_setting_success(
        self, test_client: TestClient, admin_headers, test_db
    ):
        setting = NotificationSettings(name="Delete Me", service_url="slack://token/")
        test_db.add(setting)
        test_db.commit()
        test_db.refresh(setting)

        response = test_client.delete(
            f"/api/notifications/{setting.id}", headers=admin_headers
        )

        assert response.status_code == 204
        assert (
            test_db.query(NotificationSettings)
            .filter(NotificationSettings.id == setting.id)
            .first()
            is None
        )

    def test_delete_notification_setting_not_found(
        self, test_client: TestClient, admin_headers
    ):
        response = test_client.delete(
            "/api/notifications/999999", headers=admin_headers
        )

        assert response.status_code == 404
        assert (
            response.json()["detail"]["key"]
            == "backend.errors.notifications.settingNotFound"
        )

    def test_test_notification_success(self, test_client: TestClient, admin_headers):
        with patch(
            "app.api.notifications.notification_service.test_notification",
            new=AsyncMock(return_value={"success": True, "message": "ok"}),
        ):
            response = test_client.post(
                "/api/notifications/test",
                json={"service_url": "slack://token/"},
                headers=admin_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)
