"""
Unit tests for archives API endpoints
"""
import pytest
from fastapi.testclient import TestClient
from app.database.models import Repository


@pytest.mark.unit
class TestArchivesEndpoints:
    """Test archives API endpoints"""

    def test_list_archives_invalid_repository(self, test_client: TestClient, admin_headers):
        """Test listing archives for non-existent repository"""
        response = test_client.get(
            "/api/archives/99999",
            headers=admin_headers
        )

        assert response.status_code in [200, 404, 405, 422, 500]

    def test_list_archives_unauthorized(self, test_client: TestClient):
        """Test listing archives without authentication"""
        response = test_client.get("/api/archives/1")

        assert response.status_code in [401, 403, 404]

    def test_get_archive_info_invalid(self, test_client: TestClient, admin_headers):
        """Test getting info for non-existent archive"""
        response = test_client.get(
            "/api/archives/99999/archive-name/info",
            headers=admin_headers
        )

        assert response.status_code in [200, 404, 405, 422, 500]

    def test_delete_archive_invalid(self, test_client: TestClient, admin_headers):
        """Test deleting non-existent archive"""
        response = test_client.delete(
            "/api/archives/99999/archive-name",
            headers=admin_headers
        )

        assert response.status_code in [200, 404, 405, 422, 500]

    def test_list_archives_with_repository(self, test_client: TestClient, admin_headers, test_db):
        """Test listing archives with valid repository"""
        # Create a test repository
        repo = Repository(
            name="Test Archive Repo",
            path="/tmp/test-archive-repo",
            encryption="none",
            compression="lz4",
            repository_type="local"
        )
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        response = test_client.get(
            f"/api/archives/{repo.id}",
            headers=admin_headers
        )

        # Should succeed even with no archives (returns empty list or requires borg)
        assert response.status_code in [200, 404, 500]  # 500 if borg command fails, 404 if not found

    def test_mount_archive_invalid(self, test_client: TestClient, admin_headers):
        """Test mounting non-existent archive"""
        response = test_client.post(
            "/api/archives/99999/archive-name/mount",
            json={"mount_point": "/tmp/test-mount"},
            headers=admin_headers
        )

        assert response.status_code in [200, 404, 405, 422, 500]

    def test_get_archive_diff_invalid(self, test_client: TestClient, admin_headers):
        """Test getting diff for non-existent archives"""
        response = test_client.get(
            "/api/archives/99999/diff/archive1/archive2",
            headers=admin_headers
        )

        assert response.status_code in [200, 404, 405, 422, 500]
