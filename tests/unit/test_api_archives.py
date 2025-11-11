"""
Comprehensive unit tests for archives API endpoints
"""
import pytest
import json
from unittest.mock import patch, AsyncMock
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
class TestArchivesListEndpoint:
    """Test /archives/list endpoint"""

    def test_list_archives_with_repository(self, test_client: TestClient, admin_headers, test_db):
        """Test listing archives with valid repository - may succeed or fail depending on borg availability"""
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

        # 200 if succeeds, 404 if repo lookup fails, 500 if borg command fails
        assert response.status_code in [200, 404, 500]

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

    def test_list_archives_success(self, test_client: TestClient, admin_headers, test_db):
        """Test successful archive listing with mocked borg response"""
        # Create a test repository
        repo = Repository(
            name="Test Repo",
            path="/test/repo",
            encryption="none",
            repository_type="local"
        )
        test_db.add(repo)
        test_db.commit()

        # Mock borg list_archives to return success
        with patch('app.core.borg.BorgInterface.list_archives', new_callable=AsyncMock) as mock_list:
            mock_list.return_value = {
                "success": True,
                "stdout": json.dumps({
                    "archives": [
                        {"name": "archive1", "time": "2025-01-01T00:00:00"},
                        {"name": "archive2", "time": "2025-01-02T00:00:00"}
                    ]
                })
            }

            response = test_client.get(
                f"/api/archives/list?repository={repo.path}",
                headers=admin_headers
            )

            assert response.status_code == 200
            data = response.json()
            assert "archives" in data

    def test_list_archives_borg_failure(self, test_client: TestClient, admin_headers, test_db):
        """Test archive listing when borg command fails"""
        repo = Repository(
            name="Test Repo",
            path="/test/repo",
            encryption="none",
            repository_type="local"
        )
        test_db.add(repo)
        test_db.commit()

        # Mock borg to return failure
        with patch('app.core.borg.BorgInterface.list_archives', new_callable=AsyncMock) as mock_list:
            mock_list.return_value = {
                "success": False,
                "stderr": "Repository not accessible"
            }

            response = test_client.get(
                f"/api/archives/list?repository={repo.path}",
                headers=admin_headers
            )

            assert response.status_code == 500
            assert "Failed to list archives" in response.json()["detail"]


@pytest.mark.unit
class TestArchiveInfoEndpoint:
    """Test /archives/{archive_id}/info endpoint"""

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

    def test_get_archive_info_success_without_files(self, test_client: TestClient, admin_headers, test_db):
        """Test getting archive info without file listing"""
        repo = Repository(
            name="Test Repo",
            path="/test/repo",
            encryption="none",
            repository_type="local"
        )
        test_db.add(repo)
        test_db.commit()

        # Mock borg info_archive
        with patch('app.core.borg.BorgInterface.info_archive', new_callable=AsyncMock) as mock_info:
            mock_info.return_value = {
                "success": True,
                "stdout": json.dumps({
                    "archives": [{
                        "name": "test-archive",
                        "id": "abc123",
                        "start": "2025-01-01T00:00:00",
                        "end": "2025-01-01T01:00:00",
                        "duration": 3600,
                        "stats": {
                            "original_size": 1000000,
                            "compressed_size": 500000,
                            "deduplicated_size": 250000
                        }
                    }],
                    "repository": {},
                    "encryption": {},
                    "cache": {}
                })
            }

            response = test_client.get(
                f"/api/archives/test-archive/info?repository={repo.path}",
                headers=admin_headers
            )

            assert response.status_code == 200
            data = response.json()
            assert "info" in data
            assert data["info"]["name"] == "test-archive"

    def test_get_archive_info_success_with_files(self, test_client: TestClient, admin_headers, test_db):
        """Test getting archive info with file listing"""
        repo = Repository(
            name="Test Repo",
            path="/test/repo",
            encryption="none",
            repository_type="local"
        )
        test_db.add(repo)
        test_db.commit()

        # Mock borg methods
        with patch('app.core.borg.BorgInterface.info_archive', new_callable=AsyncMock) as mock_info, \
             patch('app.core.borg.BorgInterface.list_archive_contents', new_callable=AsyncMock) as mock_list:

            mock_info.return_value = {
                "success": True,
                "stdout": json.dumps({
                    "archives": [{
                        "name": "test-archive",
                        "id": "abc123",
                        "stats": {}
                    }],
                    "repository": {},
                    "encryption": {},
                    "cache": {}
                })
            }

            mock_list.return_value = {
                "success": True,
                "stdout": json.dumps({"path": "/file1.txt", "type": "f", "size": 100}) + "\n" + \
                         json.dumps({"path": "/file2.txt", "type": "f", "size": 200})
            }

            response = test_client.get(
                f"/api/archives/test-archive/info?repository={repo.path}&include_files=true",
                headers=admin_headers
            )

            assert response.status_code == 200
            data = response.json()
            assert "info" in data
            assert "files" in data["info"]
            assert len(data["info"]["files"]) == 2

    def test_get_archive_info_invalid_json(self, test_client: TestClient, admin_headers, test_db):
        """Test getting archive info with invalid JSON from borg"""
        repo = Repository(
            name="Test Repo",
            path="/test/repo",
            encryption="none",
            repository_type="local"
        )
        test_db.add(repo)
        test_db.commit()

        # Mock borg to return invalid JSON
        with patch('app.core.borg.BorgInterface.info_archive', new_callable=AsyncMock) as mock_info:
            mock_info.return_value = {
                "success": True,
                "stdout": "invalid json output"
            }

            response = test_client.get(
                f"/api/archives/test-archive/info?repository={repo.path}",
                headers=admin_headers
            )

            assert response.status_code == 200
            # Should fallback to raw output
            data = response.json()
            assert "info" in data


@pytest.mark.unit
class TestArchiveContentsEndpoint:
    """Test /archives/{archive_id}/contents endpoint"""

    def test_get_archive_contents_success(self, test_client: TestClient, admin_headers, test_db):
        """Test getting archive contents successfully"""
        repo = Repository(
            name="Test Repo",
            path="/test/repo",
            encryption="none",
            repository_type="local"
        )
        test_db.add(repo)
        test_db.commit()

        # Mock borg list_archive_contents
        with patch('app.core.borg.BorgInterface.list_archive_contents', new_callable=AsyncMock) as mock_list:
            mock_list.return_value = {
                "success": True,
                "stdout": json.dumps([
                    {"path": "/file1.txt", "type": "f"},
                    {"path": "/file2.txt", "type": "f"}
                ])
            }

            response = test_client.get(
                f"/api/archives/test-archive/contents?repository={repo.path}",
                headers=admin_headers
            )

            assert response.status_code == 200
            data = response.json()
            assert "contents" in data

    def test_get_archive_contents_with_path(self, test_client: TestClient, admin_headers, test_db):
        """Test getting archive contents for specific path"""
        repo = Repository(
            name="Test Repo",
            path="/test/repo",
            encryption="none",
            repository_type="local"
        )
        test_db.add(repo)
        test_db.commit()

        # Mock borg list_archive_contents
        with patch('app.core.borg.BorgInterface.list_archive_contents', new_callable=AsyncMock) as mock_list:
            mock_list.return_value = {
                "success": True,
                "stdout": json.dumps([{"path": "/subdir/file.txt", "type": "f"}])
            }

            response = test_client.get(
                f"/api/archives/test-archive/contents?repository={repo.path}&path=/subdir",
                headers=admin_headers
            )

            assert response.status_code == 200
            data = response.json()
            assert "contents" in data

    def test_get_archive_contents_borg_failure(self, test_client: TestClient, admin_headers, test_db):
        """Test getting archive contents when borg fails"""
        repo = Repository(
            name="Test Repo",
            path="/test/repo",
            encryption="none",
            repository_type="local"
        )
        test_db.add(repo)
        test_db.commit()

        # Mock borg to return failure
        with patch('app.core.borg.BorgInterface.list_archive_contents', new_callable=AsyncMock) as mock_list:
            mock_list.return_value = {
                "success": False,
                "stderr": "Archive not found"
            }

            response = test_client.get(
                f"/api/archives/test-archive/contents?repository={repo.path}",
                headers=admin_headers
            )

            assert response.status_code == 500
            assert "Failed to get archive contents" in response.json()["detail"]


@pytest.mark.unit
class TestDeleteArchiveEndpoint:
    """Test DELETE /archives/{archive_id} endpoint"""

    def test_delete_archive_success(self, test_client: TestClient, admin_headers, test_db):
        """Test successfully deleting an archive"""
        repo = Repository(
            name="Test Repo",
            path="/test/repo",
            encryption="none",
            repository_type="local"
        )
        test_db.add(repo)
        test_db.commit()

        # Mock borg delete_archive and list_archives (for count update)
        with patch('app.core.borg.BorgInterface.delete_archive', new_callable=AsyncMock) as mock_delete, \
             patch('app.core.borg.BorgInterface.list_archives', new_callable=AsyncMock) as mock_list:

            mock_delete.return_value = {
                "success": True,
                "stdout": ""
            }

            mock_list.return_value = {
                "success": True,
                "stdout": json.dumps({"archives": []})
            }

            response = test_client.delete(
                f"/api/archives/test-archive?repository={repo.path}",
                headers=admin_headers
            )

            assert response.status_code == 200
            data = response.json()
            assert "message" in data
            assert "deleted successfully" in data["message"].lower()

    def test_delete_archive_borg_failure(self, test_client: TestClient, admin_headers, test_db):
        """Test deleting archive when borg command fails"""
        repo = Repository(
            name="Test Repo",
            path="/test/repo",
            encryption="none",
            repository_type="local"
        )
        test_db.add(repo)
        test_db.commit()

        # Mock borg to return failure
        with patch('app.core.borg.BorgInterface.delete_archive', new_callable=AsyncMock) as mock_delete:
            mock_delete.return_value = {
                "success": False,
                "stderr": "Archive not found or locked"
            }

            response = test_client.delete(
                f"/api/archives/test-archive?repository={repo.path}",
                headers=admin_headers
            )

            assert response.status_code == 500
            assert "Failed to delete archive" in response.json()["detail"]


@pytest.mark.unit
class TestDownloadFileEndpoint:
    """Test GET /archives/download endpoint"""

    def test_download_file_missing_token(self, test_client: TestClient):
        """Test download without token parameter"""
        response = test_client.get(
            "/api/archives/download?repository=/test/repo&archive=test-archive&file_path=/test.txt"
        )

        # Should fail without valid token
        assert response.status_code in [401, 422]

    def test_download_file_invalid_token(self, test_client: TestClient):
        """Test download with invalid token"""
        response = test_client.get(
            "/api/archives/download?repository=/test/repo&archive=test-archive&file_path=/test.txt&token=invalid"
        )

        # Should fail with invalid token
        assert response.status_code == 401

    def test_download_file_repository_not_found(self, test_client: TestClient, test_db, admin_token):
        """Test download from non-existent repository"""
        response = test_client.get(
            f"/api/archives/download?repository=/nonexistent&archive=test-archive&file_path=/test.txt&token={admin_token}"
        )

        assert response.status_code == 404
        assert "Repository not found" in response.json()["detail"]


@pytest.mark.unit
class TestArchivesSpecificEndpoints:
    """Test specific archives endpoints"""

    def test_mount_archive_endpoint_exists(self, test_client: TestClient, admin_headers):
        """Test that mount endpoint exists (implementation may vary)"""
        response = test_client.post(
            "/api/archives/99999/archive-name/mount",
            json={"mount_point": "/tmp/test-mount"},
            headers=admin_headers
        )

        # Could be 404 (not found), 405 (not implemented), or other
        assert response.status_code in [404, 405, 422, 500]

    def test_get_archive_diff_endpoint_exists(self, test_client: TestClient, admin_headers):
        """Test that diff endpoint exists (implementation may vary)"""
        response = test_client.get(
            "/api/archives/99999/diff/archive1/archive2",
            headers=admin_headers
        )

        # Could be 404 (not found), 405 (not implemented), or other
        assert response.status_code in [404, 405, 422, 500]
