"""
Unit tests for archives API endpoints

These tests focus on:
- Authentication and authorization
- Input validation
- Error handling
- Resource existence validation

Integration tests (test_api_archives_integration.py) handle:
- Real borg operations
- Archive listing, info, contents
- File downloads
- Encryption
"""
import pytest
from fastapi.testclient import TestClient
from app.database.models import Repository


@pytest.mark.unit
class TestArchivesAuthentication:
    """Test authentication and authorization for archives endpoints"""

    def test_list_archives_no_auth_returns_403(self, test_client: TestClient):
        """
        Verify unauthenticated requests are rejected.
        NOTE: FastAPI's HTTPBearer returns 403 for missing credentials.
        """
        response = test_client.get("/api/archives/list?repository=/tmp/repo")
        assert response.status_code == 403

    def test_get_archive_info_no_auth_returns_403(self, test_client: TestClient):
        """Verify unauthenticated archive info requests are rejected"""
        response = test_client.get("/api/archives/myarchive/info?repository=/tmp/repo")
        assert response.status_code == 403

    def test_get_archive_contents_no_auth_returns_403(self, test_client: TestClient):
        """Verify unauthenticated archive contents requests are rejected"""
        response = test_client.get("/api/archives/myarchive/contents?repository=/tmp/repo")
        assert response.status_code == 403

    def test_delete_archive_no_auth_returns_403(self, test_client: TestClient):
        """Verify unauthenticated archive deletion is rejected"""
        response = test_client.delete("/api/archives/myarchive?repository=/tmp/repo")
        assert response.status_code == 403


@pytest.mark.unit
class TestArchivesResourceValidation:
    """Test resource existence validation"""

    def test_list_archives_nonexistent_repository_returns_404(
        self,
        test_client: TestClient,
        admin_headers
    ):
        """Should return 404 when repository doesn't exist in database"""
        response = test_client.get(
            "/api/archives/list?repository=/nonexistent/path",
            headers=admin_headers
        )

        assert response.status_code == 404
        assert "Repository not found" in response.json()["detail"]

    def test_get_archive_info_nonexistent_repository_returns_404(
        self,
        test_client: TestClient,
        admin_headers
    ):
        """Should return 404 when repository doesn't exist in database"""
        response = test_client.get(
            "/api/archives/myarchive/info?repository=/nonexistent/path",
            headers=admin_headers
        )

        assert response.status_code == 404
        assert "Repository not found" in response.json()["detail"]

    def test_get_archive_contents_nonexistent_repository_returns_404(
        self,
        test_client: TestClient,
        admin_headers
    ):
        """Should return 404 when repository doesn't exist in database"""
        response = test_client.get(
            "/api/archives/myarchive/contents?repository=/nonexistent/path",
            headers=admin_headers
        )

        assert response.status_code == 404
        assert "Repository not found" in response.json()["detail"]

    def test_delete_archive_nonexistent_repository_returns_404(
        self,
        test_client: TestClient,
        admin_headers
    ):
        """Should return 404 when repository doesn't exist in database"""
        response = test_client.delete(
            "/api/archives/myarchive?repository=/nonexistent/path",
            headers=admin_headers
        )

        assert response.status_code == 404
        assert "Repository not found" in response.json()["detail"]


@pytest.mark.unit
class TestDownloadFileEndpoint:
    """Test GET /archives/download endpoint validation"""

    def test_download_file_missing_token(self, test_client: TestClient):
        """Test download without authentication token"""
        response = test_client.get(
            "/api/archives/download?repository=/test/repo&archive=test-archive&file_path=/test.txt"
        )

        # Should fail without valid token
        assert response.status_code in [401, 422]

    def test_download_file_invalid_token(self, test_client: TestClient):
        """Test download with invalid/expired token"""
        response = test_client.get(
            "/api/archives/download?repository=/test/repo&archive=test-archive&file_path=/test.txt&token=invalid-token"
        )

        # Should fail with invalid token
        assert response.status_code == 401

    def test_download_file_repository_not_found(
        self,
        test_client: TestClient,
        test_db,
        admin_token
    ):
        """Test download from non-existent repository"""
        response = test_client.get(
            f"/api/archives/download?repository=/nonexistent&archive=test-archive&file_path=/test.txt&token={admin_token}"
        )

        assert response.status_code == 404
        assert "Repository not found" in response.json()["detail"]
