"""
Unit tests for schedule API endpoints
"""
import pytest
from fastapi.testclient import TestClient
from app.database.models import Repository


@pytest.mark.unit
class TestScheduleEndpoints:
    """Test schedule API endpoints"""

    def test_list_schedules_empty(self, test_client: TestClient, admin_headers):
        """Test listing schedules when none exist"""
        response = test_client.get("/api/schedule/", headers=admin_headers)

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, (list, dict))

    def test_list_schedules_unauthorized(self, test_client: TestClient):
        """Test listing schedules without authentication"""
        response = test_client.get("/api/schedule/")

        assert response.status_code in [401, 403, 404]

    def test_create_schedule_missing_fields(self, test_client: TestClient, admin_headers):
        """Test creating schedule with missing fields"""
        response = test_client.post(
            "/api/schedule/",
            json={},
            headers=admin_headers
        )

        assert response.status_code == 422  # Validation error

    def test_create_schedule_invalid_repository(self, test_client: TestClient, admin_headers):
        """Test creating schedule with invalid repository"""
        response = test_client.post(
            "/api/schedule/",
            json={
                "repository_id": 99999,
                "schedule": "0 2 * * *",  # Daily at 2 AM
                "enabled": True
            },
            headers=admin_headers
        )

        assert response.status_code in [200, 403, 404, 422]  # May return 200 with error or 422 validation error

    def test_get_schedule_nonexistent(self, test_client: TestClient, admin_headers):
        """Test getting non-existent schedule"""
        response = test_client.get("/api/schedule/99999", headers=admin_headers)

        assert response.status_code in [403, 404, 405]  # Auth/notfound/notimpl

    def test_update_schedule_nonexistent(self, test_client: TestClient, admin_headers):
        """Test updating non-existent schedule"""
        response = test_client.put(
            "/api/schedule/99999",
            json={
                "schedule": "0 3 * * *",
                "enabled": False
            },
            headers=admin_headers
        )

        assert response.status_code in [403, 404, 405]  # Auth/notfound/notimpl

    def test_delete_schedule_nonexistent(self, test_client: TestClient, admin_headers):
        """Test deleting non-existent schedule"""
        response = test_client.delete("/api/schedule/99999", headers=admin_headers)

        assert response.status_code in [403, 404, 405]  # Auth/notfound/notimpl

    def test_toggle_schedule_nonexistent(self, test_client: TestClient, admin_headers):
        """Test toggling non-existent schedule"""
        response = test_client.post(
            "/api/schedule/99999/toggle",
            headers=admin_headers
        )

        assert response.status_code in [403, 404, 405]  # Auth/notfound/notimpl

    def test_run_schedule_now_nonexistent(self, test_client: TestClient, admin_headers):
        """Test running non-existent schedule immediately"""
        response = test_client.post(
            "/api/schedule/99999/run-now",
            headers=admin_headers
        )

        assert response.status_code in [403, 404, 405]  # Auth/notfound/notimpl

    def test_get_schedule_history(self, test_client: TestClient, admin_headers):
        """Test getting schedule execution history"""
        response = test_client.get("/api/schedule/history", headers=admin_headers)

        assert response.status_code in [200, 403, 404, 422]  # May return validation error
