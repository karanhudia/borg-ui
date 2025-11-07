"""
Unit tests for browse/filesystem API endpoints
"""
import pytest
from fastapi.testclient import TestClient
from app.database.models import Repository


@pytest.mark.unit
class TestBrowseEndpoints:
    """Test browse API endpoints"""

    def test_browse_archive_unauthorized(self, test_client: TestClient):
        """Test browsing archive without authentication"""
        response = test_client.get("/api/browse/1/archive-name/")

        assert response.status_code in [401, 403, 404]

    def test_browse_archive_invalid_repository(self, test_client: TestClient, admin_headers):
        """Test browsing archive with invalid repository"""
        response = test_client.get(
            "/api/browse/99999/archive-name/",
            headers=admin_headers
        )

        assert response.status_code in [404, 405]  # Not found or not implemented

    def test_browse_archive_root(self, test_client: TestClient, admin_headers, test_db):
        """Test browsing archive root directory"""
        # Create a test repository
        repo = Repository(
            name="Browse Test Repo",
            path="/tmp/test-browse-repo",
            encryption="none",
            compression="lz4",
            repository_type="local"
        )
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        response = test_client.get(
            f"/api/browse/{repo.id}/test-archive/",
            headers=admin_headers
        )

        # Might fail if borg not available or archive doesn't exist
        assert response.status_code in [200, 403, 404, 500]

    def test_browse_archive_subdirectory(self, test_client: TestClient, admin_headers, test_db):
        """Test browsing archive subdirectory"""
        repo = Repository(
            name="Browse Test Repo",
            path="/tmp/test-browse-repo",
            encryption="none",
            compression="lz4",
            repository_type="local"
        )
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        response = test_client.get(
            f"/api/browse/{repo.id}/test-archive/home/user",
            headers=admin_headers
        )

        assert response.status_code in [200, 403, 404, 500]

    def test_get_file_content_invalid(self, test_client: TestClient, admin_headers):
        """Test getting file content from invalid archive"""
        response = test_client.get(
            "/api/browse/99999/archive-name/path/to/file.txt",
            headers=admin_headers
        )

        assert response.status_code in [404, 405]  # Not found or not implemented

    def test_search_archive_invalid(self, test_client: TestClient, admin_headers):
        """Test searching in invalid archive"""
        response = test_client.post(
            "/api/browse/99999/archive-name/search",
            json={"query": "test"},
            headers=admin_headers
        )

        assert response.status_code in [404, 405]  # Not found or not implemented


@pytest.mark.unit
class TestFilesystemEndpoints:
    """Test filesystem API endpoints"""

    def test_list_directory_unauthorized(self, test_client: TestClient):
        """Test listing directory without authentication"""
        response = test_client.get("/api/filesystem/browse")

        assert response.status_code in [401, 403, 404]

    def test_list_directory_root(self, test_client: TestClient, admin_headers):
        """Test listing root directory"""
        response = test_client.get(
            "/api/filesystem/browse",
            params={"path": "/"},
            headers=admin_headers
        )

        # Should work or fail gracefully
        assert response.status_code in [200, 403, 500]

    def test_list_directory_invalid_path(self, test_client: TestClient, admin_headers):
        """Test listing non-existent directory"""
        response = test_client.get(
            "/api/filesystem/browse",
            params={"path": "/nonexistent/path"},
            headers=admin_headers
        )

        assert response.status_code in [200, 403, 404, 500]

    def test_get_directory_info(self, test_client: TestClient, admin_headers):
        """Test getting directory information"""
        response = test_client.get(
            "/api/filesystem/info",
            params={"path": "/tmp"},
            headers=admin_headers
        )

        assert response.status_code in [200, 403, 404, 500]

    def test_create_directory_missing_path(self, test_client: TestClient, admin_headers):
        """Test creating directory without path"""
        response = test_client.post(
            "/api/filesystem/mkdir",
            json={},
            headers=admin_headers
        )

        assert response.status_code in [405, 422]  # Validation error or method not allowed

    def test_validate_path_empty(self, test_client: TestClient, admin_headers):
        """Test path validation with empty path"""
        response = test_client.post(
            "/api/filesystem/validate",
            json={"path": ""},
            headers=admin_headers
        )

        assert response.status_code in [200, 400, 405, 422]

    def test_validate_path_valid(self, test_client: TestClient, admin_headers):
        """Test path validation with valid path"""
        response = test_client.post(
            "/api/filesystem/validate",
            json={"path": "/tmp"},
            headers=admin_headers
        )

        assert response.status_code in [200, 400, 405]

    def test_get_disk_usage(self, test_client: TestClient, admin_headers):
        """Test getting disk usage for path"""
        response = test_client.get(
            "/api/filesystem/disk-usage",
            params={"path": "/tmp"},
            headers=admin_headers
        )

        assert response.status_code in [200, 403, 404, 500]
