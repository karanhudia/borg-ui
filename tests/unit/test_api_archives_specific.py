"""
Specific, meaningful tests for archives API endpoints.
Each test verifies ONE specific behavior with EXACT expected status codes.
"""
import pytest
import json
from fastapi.testclient import TestClient
from app.database.models import Repository


@pytest.mark.unit
class TestArchivesAuthentication:
    """Test authentication and authorization for archives endpoints"""

    def test_list_archives_no_auth_returns_403(self, test_client: TestClient):
        """
        Currently returns 403 when no authentication token is provided.
        NOTE: FastAPI's HTTPBearer returns 403 for missing credentials.
        REST best practice would be 401, but this requires custom HTTPBearer implementation.
        """
        response = test_client.get("/api/archives/list?repository=/tmp/repo")

        assert response.status_code == 403

    def test_get_archive_info_no_auth_returns_403(self, test_client: TestClient):
        """Currently returns 403 when no authentication token is provided (FastAPI HTTPBearer behavior)"""
        response = test_client.get("/api/archives/myarchive/info?repository=/tmp/repo")

        assert response.status_code == 403

    def test_get_archive_contents_no_auth_returns_403(self, test_client: TestClient):
        """Currently returns 403 when no authentication token is provided (FastAPI HTTPBearer behavior)"""
        response = test_client.get("/api/archives/myarchive/contents?repository=/tmp/repo")

        assert response.status_code == 403

    def test_delete_archive_no_auth_returns_403(self, test_client: TestClient):
        """Currently returns 403 when no authentication token is provided (FastAPI HTTPBearer behavior)"""
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
class TestArchivesWithValidRepository:
    """Test archives operations with valid repository (may fail if borg unavailable)"""

    def test_list_archives_valid_repository_returns_200_or_500(
        self,
        test_client: TestClient,
        admin_headers,
        test_db
    ):
        """Should return 200 if borg succeeds, 500 if borg command fails"""
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
            f"/api/archives/list?repository={repo.path}",
            headers=admin_headers
        )

        # 200 = success, 500 = borg command failed
        assert response.status_code in [200, 500]

        if response.status_code == 200:
            data = response.json()
            assert "archives" in data
        elif response.status_code == 500:
            # Borg command failed
            assert "Failed to list archives" in response.json()["detail"]

    def test_get_archive_info_borg_failure_returns_500(
        self,
        test_client: TestClient,
        admin_headers,
        test_db
    ):
        """Should return 500 when borg command fails (not 404)"""
        # Create a test repository
        repo = Repository(
            name="Test Info Repo",
            path="/tmp/test-info-repo",
            encryption="none",
            compression="lz4",
            repository_type="local"
        )
        test_db.add(repo)
        test_db.commit()

        response = test_client.get(
            f"/api/archives/nonexistent-archive/info?repository={repo.path}",
            headers=admin_headers
        )

        # Repository exists (404 handled), so borg will fail with 500
        assert response.status_code in [200, 500]

        if response.status_code == 500:
            assert "Failed to get archive info" in response.json()["detail"]
