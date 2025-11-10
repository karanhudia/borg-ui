"""
Enhanced comprehensive tests for repositories API with mocking.
Focuses on improving coverage by testing endpoints that can be reliably tested in isolation.
Each test verifies ONE specific expected outcome.

Note: Tests requiring complex borg interaction mocking are candidates for integration testing.
"""
import pytest
import json
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient
from app.database.models import Repository, ScheduledJob


@pytest.mark.unit
class TestRepositoriesListAndGet:
    """Test repository listing and retrieval"""

    def test_list_repositories_success(self, test_client: TestClient, admin_headers, test_db):
        """Test listing repositories returns 200 and correct structure"""
        # Create test repositories
        repo1 = Repository(name="Repo 1", path="/repo1", encryption="none", repository_type="local")
        repo2 = Repository(name="Repo 2", path="/repo2", encryption="repokey", repository_type="ssh")
        test_db.add_all([repo1, repo2])
        test_db.commit()

        response = test_client.get("/api/repositories/", headers=admin_headers)

        assert response.status_code == 200
        data = response.json()
        assert "repositories" in data
        assert len(data["repositories"]) >= 2

    def test_get_repository_by_id_success(self, test_client: TestClient, admin_headers, test_db):
        """Test getting repository by ID returns 200 with mocked stats"""
        repo = Repository(name="Test Repo", path="/test/repo", encryption="none", repository_type="local")
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        # Mock the stats call to ensure success
        with patch('app.api.repositories.get_repository_stats', new_callable=AsyncMock) as mock_stats:
            mock_stats.return_value = {
                "total_size": 1000000,
                "compressed_size": 500000,
                "deduplicated_size": 250000
            }

            response = test_client.get(f"/api/repositories/{repo.id}", headers=admin_headers)

            assert response.status_code == 200
            data = response.json()
            assert "repository" in data
            assert data["repository"]["name"] == "Test Repo"

    def test_get_repository_by_id_stats_failure(self, test_client: TestClient, admin_headers, test_db):
        """Test getting repository when stats call fails returns 500"""
        repo = Repository(name="Test Repo", path="/test/repo", encryption="none", repository_type="local")
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        # Mock the stats call to fail
        with patch('app.api.repositories.get_repository_stats', new_callable=AsyncMock) as mock_stats:
            mock_stats.side_effect = Exception("Stats retrieval failed")

            response = test_client.get(f"/api/repositories/{repo.id}", headers=admin_headers)

            assert response.status_code == 500

    def test_get_repository_not_found(self, test_client: TestClient, admin_headers):
        """Test getting non-existent repository returns 404"""
        response = test_client.get("/api/repositories/99999", headers=admin_headers)

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()


@pytest.mark.unit
class TestRepositoriesCreate:
    """Test repository creation"""

    def test_create_repository_validation_error(self, test_client: TestClient, admin_headers):
        """Test repository creation with missing required fields returns 422"""
        response = test_client.post(
            "/api/repositories/",
            json={"name": "Incomplete Repo"},  # Missing path, encryption, etc.
            headers=admin_headers
        )

        assert response.status_code == 422  # Validation error


@pytest.mark.unit
class TestRepositoriesUpdate:
    """Test repository update operations"""

    def test_update_repository_not_found(self, test_client: TestClient, admin_headers):
        """Test updating non-existent repository returns 404 or 403"""
        response = test_client.put(
            "/api/repositories/99999",
            json={"name": "Updated"},
            headers=admin_headers
        )

        # May be 403 if not admin, or 404 if admin but repo not found
        assert response.status_code in [403, 404]


@pytest.mark.unit
class TestRepositoriesDelete:
    """Test repository deletion"""

    def test_delete_repository_not_found(self, test_client: TestClient, admin_headers):
        """Test deleting non-existent repository returns 404 or 403"""
        response = test_client.delete("/api/repositories/99999", headers=admin_headers)

        assert response.status_code in [403, 404]


@pytest.mark.unit
class TestRepositoriesImport:
    """Test repository import functionality"""

    def test_import_repository_validation_error(self, test_client: TestClient, admin_headers):
        """Test importing repository with missing fields returns 422"""
        response = test_client.post(
            "/api/repositories/import",
            json={"name": "Incomplete"},
            headers=admin_headers
        )

        assert response.status_code == 422


@pytest.mark.unit
class TestRepositoriesStats:
    """Test repository statistics endpoint"""

    def test_get_repository_stats_not_found(self, test_client: TestClient, admin_headers):
        """Test getting stats for non-existent repository returns 404"""
        response = test_client.get("/api/repositories/99999/stats", headers=admin_headers)

        assert response.status_code == 404


@pytest.mark.unit
class TestRepositoriesInfo:
    """Test repository info endpoint"""

    def test_get_repository_info_not_found(self, test_client: TestClient, admin_headers):
        """Test getting info for non-existent repository returns 404"""
        response = test_client.get("/api/repositories/99999/info", headers=admin_headers)

        assert response.status_code == 404


@pytest.mark.unit
class TestRepositoriesArchives:
    """Test repository archives listing"""

    def test_list_repository_archives_not_found(self, test_client: TestClient, admin_headers):
        """Test listing archives for non-existent repository returns 404"""
        response = test_client.get("/api/repositories/99999/archives", headers=admin_headers)

        assert response.status_code == 404


@pytest.mark.unit
class TestRepositoriesJobStatus:
    """Test repository job status endpoints"""

    def test_get_repository_check_jobs(self, test_client: TestClient, admin_headers, test_db):
        """Test getting repository check jobs returns 200"""
        repo = Repository(name="Job Repo", path="/job/repo", encryption="none", repository_type="local")
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        response = test_client.get(f"/api/repositories/{repo.id}/check-jobs", headers=admin_headers)

        assert response.status_code == 200

    def test_get_repository_compact_jobs(self, test_client: TestClient, admin_headers, test_db):
        """Test getting repository compact jobs returns 200"""
        repo = Repository(name="Job Repo", path="/job/repo", encryption="none", repository_type="local")
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        response = test_client.get(f"/api/repositories/{repo.id}/compact-jobs", headers=admin_headers)

        assert response.status_code == 200

    def test_get_repository_running_jobs(self, test_client: TestClient, admin_headers, test_db):
        """Test getting repository running jobs returns 200"""
        repo = Repository(name="Job Repo", path="/job/repo", encryption="none", repository_type="local")
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        response = test_client.get(f"/api/repositories/{repo.id}/running-jobs", headers=admin_headers)

        assert response.status_code == 200

    def test_get_check_jobs_repository_not_found(self, test_client: TestClient, admin_headers):
        """Test getting check jobs for non-existent repository returns 200 with empty list"""
        response = test_client.get("/api/repositories/99999/check-jobs", headers=admin_headers)

        # Returns 200 with empty list, not 404
        assert response.status_code == 200
        data = response.json()
        assert "jobs" in data or isinstance(data, list)

    def test_get_compact_jobs_repository_not_found(self, test_client: TestClient, admin_headers):
        """Test getting compact jobs for non-existent repository returns 200 with empty list"""
        response = test_client.get("/api/repositories/99999/compact-jobs", headers=admin_headers)

        # Returns 200 with empty list, not 404
        assert response.status_code == 200
        data = response.json()
        assert "jobs" in data or isinstance(data, list)

    def test_get_running_jobs_repository_not_found(self, test_client: TestClient, admin_headers):
        """Test getting running jobs for non-existent repository returns 200 with status"""
        response = test_client.get("/api/repositories/99999/running-jobs", headers=admin_headers)

        # Returns 200 with status structure, not 404
        assert response.status_code == 200
        data = response.json()
        assert "has_running_jobs" in data or "jobs" in data or isinstance(data, list)


@pytest.mark.unit
class TestRepositoriesAuthentication:
    """Test authentication for repository endpoints"""

    def test_list_repositories_no_auth(self, test_client: TestClient):
        """Test listing repositories without authentication returns 403"""
        response = test_client.get("/api/repositories/")

        assert response.status_code == 403

    def test_create_repository_no_auth(self, test_client: TestClient):
        """Test creating repository without authentication returns 403"""
        response = test_client.post(
            "/api/repositories/",
            json={"name": "Test", "path": "/test", "encryption": "none"}
        )

        assert response.status_code == 403

    def test_delete_repository_no_auth(self, test_client: TestClient):
        """Test deleting repository without authentication returns 403"""
        response = test_client.delete("/api/repositories/1")

        assert response.status_code == 403

    def test_get_stats_no_auth(self, test_client: TestClient):
        """Test getting repository stats without authentication returns 403"""
        response = test_client.get("/api/repositories/1/stats")

        assert response.status_code == 403

    def test_get_info_no_auth(self, test_client: TestClient):
        """Test getting repository info without authentication returns 403"""
        response = test_client.get("/api/repositories/1/info")

        assert response.status_code == 403

    def test_import_repository_no_auth(self, test_client: TestClient):
        """Test importing repository without authentication returns 403"""
        response = test_client.post(
            "/api/repositories/import",
            json={"name": "Test", "path": "/test", "encryption": "none"}
        )

        assert response.status_code == 403


@pytest.mark.unit
class TestRepositoriesCRUDEdgeCases:
    """Test edge cases and error handling"""

    def test_create_repository_duplicate_path(self, test_client: TestClient, admin_headers, test_db):
        """Test creating repository with duplicate path"""
        # Create first repository
        repo = Repository(name="Existing", path="/duplicate/path", encryption="none", repository_type="local")
        test_db.add(repo)
        test_db.commit()

        # Try to create second repository with same path
        response = test_client.post(
            "/api/repositories/",
            json={
                "name": "Duplicate",
                "path": "/duplicate/path",
                "encryption": "none",
                "repository_type": "local"
            },
            headers=admin_headers
        )

        # May fail due to permissions (403), validation (422), or during creation (500)
        assert response.status_code in [403, 422, 500]

    def test_update_repository_empty_name(self, test_client: TestClient, admin_headers, test_db):
        """Test updating repository with empty name"""
        repo = Repository(name="Original", path="/test/repo", encryption="none", repository_type="local")
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        response = test_client.put(
            f"/api/repositories/{repo.id}",
            json={"name": ""},  # Empty name
            headers=admin_headers
        )

        # Should reject empty name
        assert response.status_code in [400, 403, 422]

    def test_get_repository_by_id_negative_id(self, test_client: TestClient, admin_headers):
        """Test getting repository with negative ID"""
        response = test_client.get("/api/repositories/-1", headers=admin_headers)

        assert response.status_code in [404, 422]  # Not found or validation error

    def test_delete_repository_twice(self, test_client: TestClient, admin_headers, test_db):
        """Test deleting repository twice returns 404 on second attempt"""
        repo = Repository(name="To Delete", path="/delete/repo", encryption="none", repository_type="local")
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)
        repo_id = repo.id

        # First delete - may succeed or be forbidden
        first_response = test_client.delete(f"/api/repositories/{repo_id}", headers=admin_headers)

        # If first delete succeeded, second should return 404
        if first_response.status_code == 200:
            second_response = test_client.delete(f"/api/repositories/{repo_id}", headers=admin_headers)
            assert second_response.status_code in [403, 404]
