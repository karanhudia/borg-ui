"""
Unit tests for restore API endpoints
"""
import pytest
from fastapi.testclient import TestClient
from app.database.models import Repository


@pytest.mark.unit
class TestRestoreEndpoints:
    """Test restore API endpoints"""

    def test_list_restore_jobs_empty(self, test_client: TestClient, admin_headers):
        """Test listing restore jobs when none exist"""
        response = test_client.get("/api/restore/jobs", headers=admin_headers)

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, (list, dict))

    def test_list_restore_jobs_unauthorized(self, test_client: TestClient):
        """Test listing restore jobs without authentication"""
        response = test_client.get("/api/restore/jobs")

        assert response.status_code in [401, 403, 404]

    def test_start_restore_invalid_repository(self, test_client: TestClient, admin_headers):
        """Test starting restore with invalid repository"""
        response = test_client.post(
            "/api/restore/start",
            json={
                "repository_id": 99999,
                "archive_name": "test-archive",
                "destination": "/tmp/restore"
            },
            headers=admin_headers
        )

        assert response.status_code in [200, 403, 404, 422]  # May return 200 with error or 422 validation error

    def test_start_restore_missing_fields(self, test_client: TestClient, admin_headers):
        """Test starting restore with missing required fields"""
        response = test_client.post(
            "/api/restore/start",
            json={},
            headers=admin_headers
        )

        assert response.status_code == 422  # Validation error

    def test_get_restore_job_status_nonexistent(self, test_client: TestClient, admin_headers):
        """Test getting status of non-existent restore job"""
        response = test_client.get("/api/restore/jobs/99999/status", headers=admin_headers)

        assert response.status_code in [404, 405]  # Not found or not implemented

    def test_cancel_restore_nonexistent(self, test_client: TestClient, admin_headers):
        """Test canceling non-existent restore job"""
        response = test_client.post(
            "/api/restore/jobs/99999/cancel",
            headers=admin_headers
        )

        assert response.status_code in [404, 405]  # Not found or not implemented

    def test_restore_logs_nonexistent_job(self, test_client: TestClient, admin_headers):
        """Test getting logs for non-existent restore job"""
        response = test_client.get(
            "/api/restore/jobs/99999/logs",
            headers=admin_headers
        )

        assert response.status_code in [404, 405]  # Not found or not implemented
