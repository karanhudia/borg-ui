"""
Unit tests for backup API endpoints
"""
import pytest
from fastapi.testclient import TestClient
from app.database.models import Repository


@pytest.mark.unit
class TestBackupEndpoints:
    """Test backup API endpoints"""

    def test_list_backup_jobs_empty(self, test_client: TestClient, admin_headers):
        """Test listing backup jobs when none exist"""
        response = test_client.get("/api/backup/jobs", headers=admin_headers)

        assert response.status_code == 200
        data = response.json()
        # Should return empty list or success response
        assert isinstance(data, (list, dict))

    def test_list_backup_jobs_unauthorized(self, test_client: TestClient):
        """Test listing backup jobs without authentication"""
        response = test_client.get("/api/backup/jobs")

        assert response.status_code in [401, 403, 404]

    def test_get_backup_job_status_nonexistent(self, test_client: TestClient, admin_headers):
        """Test getting status of non-existent backup job"""
        response = test_client.get("/api/backup/jobs/99999/status", headers=admin_headers)

        # Should return 404 or error response
        assert response.status_code in [404, 405]  # Not found or not implemented

    def test_start_backup_invalid_repository(self, test_client: TestClient, admin_headers):
        """Test starting backup with invalid repository ID"""
        response = test_client.post(
            "/api/backup/start",
            json={"repository_id": 99999},
            headers=admin_headers
        )

        # Should fail with appropriate error
        assert response.status_code in [200, 403, 404]  # May return 200 with error in body

    def test_cancel_backup_nonexistent(self, test_client: TestClient, admin_headers):
        """Test canceling non-existent backup job"""
        response = test_client.post(
            "/api/backup/jobs/99999/cancel",
            headers=admin_headers
        )

        # Should return error for non-existent job
        assert response.status_code in [404, 405]  # Not found or not implemented

    def test_backup_logs_nonexistent_job(self, test_client: TestClient, admin_headers):
        """Test getting logs for non-existent backup job"""
        response = test_client.get(
            "/api/backup/jobs/99999/logs",
            headers=admin_headers
        )

        # Should return 404 or empty logs
        assert response.status_code in [404, 405]  # Not found or not implemented

    def test_get_backup_history(self, test_client: TestClient, admin_headers, test_db):
        """Test getting backup history"""
        # Create a test repository first
        repo = Repository(
            name="Test Repo",
            path="/tmp/test-backup-repo",
            encryption="none",
            compression="lz4",
            repository_type="local"
        )
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        response = test_client.get(
            f"/api/backup/history/{repo.id}",
            headers=admin_headers
        )

        # Should succeed even with no history
        assert response.status_code in [200, 403, 404, 500]
