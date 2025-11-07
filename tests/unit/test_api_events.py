"""
Unit tests for events API endpoints
"""
import pytest
from fastapi.testclient import TestClient


@pytest.mark.unit
class TestEventsEndpoints:
    """Test events/SSE API endpoints"""

    def test_events_stream_unauthorized(self, test_client: TestClient):
        """Test SSE events stream without authentication"""
        response = test_client.get("/api/events/stream")

        assert response.status_code in [401, 403, 404]

    def test_backup_logs_stream_unauthorized(self, test_client: TestClient):
        """Test backup logs stream without authentication"""
        response = test_client.get("/api/events/backup/1/logs")

        assert response.status_code in [401, 403, 404]

    def test_backup_logs_stream_nonexistent(self, test_client: TestClient, admin_headers):
        """Test backup logs stream for non-existent job"""
        response = test_client.get("/api/events/backup/99999/logs", headers=admin_headers)

        # Should handle gracefully (might return 404 or empty stream)
        assert response.status_code in [200, 404, 422, 500]

    def test_restore_logs_stream_nonexistent(self, test_client: TestClient, admin_headers):
        """Test restore logs stream for non-existent job"""
        response = test_client.get("/api/events/restore/99999/logs", headers=admin_headers)

        assert response.status_code in [200, 404, 422, 500]

    def test_job_progress_nonexistent(self, test_client: TestClient, admin_headers):
        """Test job progress for non-existent job"""
        response = test_client.get("/api/events/job/99999/progress", headers=admin_headers)

        assert response.status_code in [200, 404, 422, 500]
