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
from unittest.mock import AsyncMock, patch

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
        assert response.status_code == 401

    def test_get_archive_info_no_auth_returns_403(self, test_client: TestClient):
        """Verify unauthenticated archive info requests are rejected"""
        response = test_client.get("/api/archives/myarchive/info?repository=/tmp/repo")
        assert response.status_code == 401

    def test_get_archive_contents_no_auth_returns_403(self, test_client: TestClient):
        """Verify unauthenticated archive contents requests are rejected"""
        response = test_client.get("/api/archives/myarchive/contents?repository=/tmp/repo")
        assert response.status_code == 401

    def test_delete_archive_no_auth_returns_403(self, test_client: TestClient):
        """Verify unauthenticated archive deletion is rejected"""
        response = test_client.delete("/api/archives/myarchive?repository=/tmp/repo")
        assert response.status_code == 401


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
        assert response.json()["detail"]["key"] == "backend.errors.restore.repositoryNotFound"


@pytest.mark.unit
class TestArchivesSshEnvironment:
    def test_list_archives_uses_repo_ssh_environment(
        self,
        test_client: TestClient,
        admin_headers,
        test_db,
    ):
        repo = Repository(
            name="SSH Repo",
            path="ssh://borgsmoke@127.0.0.1:2222/home/borgsmoke/remote-repo",
            repository_type="ssh",
            connection_id=1,
            passphrase=None,
        )
        test_db.add(repo)
        test_db.commit()

        fake_key_path = "/tmp/test-ssh.key"
        with patch("app.api.archives.resolve_repo_ssh_key_file", return_value=fake_key_path), \
             patch("app.api.archives.os.path.exists", side_effect=lambda path: path == fake_key_path), \
             patch("app.api.archives.os.unlink") as mock_unlink, \
             patch(
                 "app.api.archives.borg.list_archives",
                 new=AsyncMock(return_value={"success": True, "stdout": {"archives": []}}),
             ) as mock_list_archives:
            response = test_client.get(
                f"/api/archives/list?repository={repo.path}",
                headers=admin_headers,
            )

        assert response.status_code == 200
        _, kwargs = mock_list_archives.await_args
        assert kwargs["env"]["BORG_RSH"].startswith("ssh -i /tmp/test-ssh.key")
        mock_unlink.assert_called_once_with(fake_key_path)

    def test_archive_info_uses_repo_ssh_environment_for_contents(
        self,
        test_client: TestClient,
        admin_headers,
        test_db,
    ):
        repo = Repository(
            name="SSH Repo",
            path="ssh://borgsmoke@127.0.0.1:2222/home/borgsmoke/remote-repo",
            repository_type="ssh",
            connection_id=1,
            passphrase=None,
        )
        test_db.add(repo)
        test_db.commit()

        with patch("app.api.archives.resolve_repo_ssh_key_file", return_value=None), \
             patch(
                 "app.api.archives.borg.info_archive",
                 new=AsyncMock(return_value={"success": True, "stdout": '{"archives":[{"name":"arch1"}]}'}),
             ) as mock_info_archive, \
             patch(
                 "app.api.archives.borg.list_archive_contents",
                 new=AsyncMock(return_value={"success": True, "stdout": ""}),
             ) as mock_list_contents:
            response = test_client.get(
                f"/api/archives/arch1/info?repository={repo.path}&include_files=true",
                headers=admin_headers,
            )

        assert response.status_code == 200
        _, info_kwargs = mock_info_archive.await_args
        _, contents_kwargs = mock_list_contents.await_args
        assert "BORG_RSH" in info_kwargs["env"]
        assert "BORG_RSH" in contents_kwargs["env"]

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
        assert response.json()["detail"]["key"] == "backend.errors.restore.repositoryNotFound"

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
        assert response.json()["detail"]["key"] == "backend.errors.restore.repositoryNotFound"

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
        assert response.json()["detail"]["key"] == "backend.errors.restore.repositoryNotFound"


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

    def test_download_file_authorized_with_bearer_header(
        self,
        test_client: TestClient,
        admin_headers
    ):
        """Download endpoint should accept standard bearer auth without query token."""
        response = test_client.get(
            "/api/archives/download?repository=/nonexistent&archive=test-archive&file_path=/test.txt",
            headers=admin_headers
        )

        assert response.status_code == 404
        assert response.json()["detail"]["key"] == "backend.errors.archives.repositoryNotFound"

    def test_download_file_proxy_auth_without_token(
        self,
        test_client: TestClient,
        monkeypatch
    ):
        """Proxy-auth mode should not require a JWT query token for downloads."""
        from app import config

        monkeypatch.setattr(config.settings, "disable_authentication", True)

        response = test_client.get(
            "/api/archives/download?repository=/nonexistent&archive=test-archive&file_path=/test.txt",
            headers={"X-Forwarded-User": "proxyuser"}
        )

        assert response.status_code == 404
        assert response.json()["detail"]["key"] == "backend.errors.archives.repositoryNotFound"

    def test_download_file_repository_not_found(
        self,
        test_client: TestClient,
        test_db,
        admin_headers
    ):
        """Test download from non-existent repository"""
        response = test_client.get(
            "/api/archives/download?repository=/nonexistent&archive=test-archive&file_path=/test.txt",
            headers=admin_headers
        )

        assert response.status_code == 404
        assert response.json()["detail"]["key"] == "backend.errors.archives.repositoryNotFound"
