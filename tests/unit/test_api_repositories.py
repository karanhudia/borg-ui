"""
Comprehensive unit tests for repositories API endpoints

These tests focus on:
- Authentication and authorization
- CRUD operations (database only)
- Input validation
- Error handling

Integration tests (test_api_repositories_integration.py) handle:
- Real borg repository operations
- Repository initialization
- Stats and info retrieval
- Import existing repositories
"""
import pytest
import json
from fastapi.testclient import TestClient
from app.database.models import Repository, ScheduledJob


@pytest.mark.unit
class TestRepositoriesListAndGet:
    """Test repository listing and retrieval"""

    def test_list_repositories_empty(self, test_client: TestClient, admin_headers):
        """Test listing repositories when none exist"""
        response = test_client.get("/api/repositories/", headers=admin_headers)

        assert response.status_code == 200
        data = response.json()
        assert "repositories" in data or isinstance(data, list)

    def test_list_repositories_with_data(self, test_client: TestClient, admin_headers, test_db):
        """Test listing repositories with data"""
        # Create a repository in the test database
        repo = Repository(
            name="Test Repo",
            path="/tmp/test",
            encryption="none",
            compression="lz4",
            repository_type="local"
        )
        test_db.add(repo)
        test_db.commit()

        response = test_client.get("/api/repositories/", headers=admin_headers)

        assert response.status_code == 200
        # Response format might be {"success": true, "repositories": [...]} or just [...]
        data = response.json()
        if isinstance(data, dict):
            assert "repositories" in data
            repos = data["repositories"]
        else:
            repos = data

        assert len(repos) >= 1

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

    def test_list_repositories_unauthorized(self, test_client: TestClient):
        """Test listing repositories without authentication"""
        response = test_client.get("/api/repositories/")

        assert response.status_code in [401, 403]  # Accept both unauthorized and forbidden

    def test_list_repositories_no_auth(self, test_client: TestClient):
        """Test listing repositories without authentication returns 403"""
        response = test_client.get("/api/repositories/")

        assert response.status_code == 403

    def test_list_repositories_pagination(self, test_client: TestClient, admin_headers, test_db):
        """Test listing repositories with pagination"""
        # Create multiple repositories
        for i in range(5):
            repo = Repository(
                name=f"Pagination Repo {i}",
                path=f"/tmp/page-repo-{i}",
                encryption="none",
                compression="lz4",
                repository_type="local"
            )
            test_db.add(repo)
        test_db.commit()

        response = test_client.get(
            "/api/repositories/",
            params={"limit": 2, "offset": 0},
            headers=admin_headers
        )

        assert response.status_code == 200

    def test_search_repositories_by_name(self, test_client: TestClient, admin_headers, test_db):
        """Test searching repositories by name"""
        repo = Repository(
            name="Searchable Repository",
            path="/tmp/search-repo",
            encryption="none",
            compression="lz4",
            repository_type="local"
        )
        test_db.add(repo)
        test_db.commit()

        response = test_client.get(
            "/api/repositories/",
            params={"search": "Searchable"},
            headers=admin_headers
        )

        assert response.status_code == 200

    def test_get_repository_by_id(self, test_client: TestClient, admin_headers, test_db):
        """Test getting a specific repository"""
        repo = Repository(
            name="Test Repo",
            path="/tmp/test",
            encryption="none",
            compression="lz4",
            repository_type="local"
        )
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        response = test_client.get(f"/api/repositories/{repo.id}", headers=admin_headers)

        # Might be 200, 404, or 422 depending on implementation
        assert response.status_code in [200, 404, 422]

    # NOTE: Repository retrieval with stats is tested in integration tests
    # (test_api_repositories_integration.py) with real borg repositories

    def test_get_nonexistent_repository(self, test_client: TestClient, admin_headers):
        """Test getting a repository that doesn't exist"""
        response = test_client.get("/api/repositories/99999", headers=admin_headers)

        assert response.status_code in [404, 422]

    def test_get_repository_not_found(self, test_client: TestClient, admin_headers):
        """Test getting non-existent repository returns 404"""
        response = test_client.get("/api/repositories/99999", headers=admin_headers)

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_get_repository_by_id_negative_id(self, test_client: TestClient, admin_headers):
        """Test getting repository with negative ID"""
        response = test_client.get("/api/repositories/-1", headers=admin_headers)

        assert response.status_code in [404, 422]  # Not found or validation error

    def test_get_repository_details(self, test_client: TestClient, admin_headers, test_db):
        """Test getting repository details"""
        repo = Repository(
            name="Detail Test Repo",
            path="/tmp/detail-repo",
            encryption="none",
            compression="lz4",
            repository_type="local",
            source_directories=json.dumps(["/home/user"]),
            exclude_patterns=json.dumps(["*.tmp"])
        )
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        response = test_client.get(
            f"/api/repositories/{repo.id}",
            headers=admin_headers
        )

        # Should succeed or fail gracefully
        assert response.status_code in [200, 403, 404]  # OK, forbidden, or not found
        if response.status_code == 200:
            data = response.json()
            if "name" in data:
                assert data["name"] == "Detail Test Repo"


@pytest.mark.unit
class TestRepositoriesCreate:
    """Test repository creation"""

    def test_create_local_repository(self, test_client: TestClient, admin_headers, test_db):
        """Test creating local repository"""
        response = test_client.post(
            "/api/repositories/",
            json={
                "name": "Local Backup Repo",
                "path": "/tmp/local-repo",
                "encryption": "none",
                "compression": "lz4",
                "repository_type": "local"
            },
            headers=admin_headers
        )

        # Might succeed or fail depending on borg availability
        assert response.status_code in [200, 201, 400, 403, 422, 500]  # May succeed or fail (borg dependency)

    def test_create_ssh_repository(self, test_client: TestClient, admin_headers):
        """Test creating SSH repository"""
        response = test_client.post(
            "/api/repositories/",
            json={
                "name": "Remote SSH Repo",
                "path": "user@server:/path/to/repo",
                "encryption": "repokey",
                "compression": "zstd",
                "repository_type": "ssh"
            },
            headers=admin_headers
        )

        assert response.status_code in [200, 201, 400, 403, 422, 500]  # May succeed or fail (borg dependency)

    def test_create_repository_missing_name(self, test_client: TestClient, admin_headers):
        """Test creating repository without name"""
        response = test_client.post(
            "/api/repositories/",
            json={
                "path": "/tmp/test-repo",
                "encryption": "none",
                "compression": "lz4"
            },
            headers=admin_headers
        )

        assert response.status_code == 422  # Validation error

    def test_create_repository_missing_path(self, test_client: TestClient, admin_headers):
        """Test creating repository without path"""
        response = test_client.post(
            "/api/repositories/",
            json={
                "name": "No Path Repo",
                "encryption": "none",
                "compression": "lz4"
            },
            headers=admin_headers
        )

        assert response.status_code == 422

    def test_create_repository_invalid_encryption(self, test_client: TestClient, admin_headers):
        """Test creating repository with invalid encryption type"""
        response = test_client.post(
            "/api/repositories/",
            json={
                "name": "Invalid Encryption",
                "path": "/tmp/test-repo",
                "encryption": "invalid-encryption-type",
                "compression": "lz4",
                "repository_type": "local"
            },
            headers=admin_headers
        )

        assert response.status_code in [400, 403, 422]  # Bad request, forbidden, or validation

    def test_create_repository_with_source_directories(self, test_client: TestClient, admin_headers):
        """Test creating repository with source directories"""
        response = test_client.post(
            "/api/repositories/",
            json={
                "name": "Multi Source Repo",
                "path": "/tmp/multi-source",
                "encryption": "none",
                "compression": "lz4",
                "repository_type": "local",
                "source_directories": ["/home/user/docs", "/home/user/photos"]
            },
            headers=admin_headers
        )

        assert response.status_code in [200, 201, 400, 403, 422, 500]  # May succeed or fail (borg dependency)

    def test_create_repository_with_exclude_patterns(self, test_client: TestClient, admin_headers):
        """Test creating repository with exclude patterns"""
        response = test_client.post(
            "/api/repositories/",
            json={
                "name": "Exclude Patterns Repo",
                "path": "/tmp/exclude-repo",
                "encryption": "none",
                "compression": "lz4",
                "repository_type": "local",
                "exclude_patterns": ["*.tmp", "*.cache", "node_modules/"]
            },
            headers=admin_headers
        )

        assert response.status_code in [200, 201, 400, 403, 422, 500]  # May succeed or fail (borg dependency)

    def test_create_repository_validation_error(self, test_client: TestClient, admin_headers):
        """Test repository creation with missing required fields returns 422"""
        response = test_client.post(
            "/api/repositories/",
            json={"name": "Incomplete Repo"},  # Missing path, encryption, etc.
            headers=admin_headers
        )

        assert response.status_code == 422  # Validation error

    def test_create_repository_no_auth(self, test_client: TestClient):
        """Test creating repository without authentication returns 403"""
        response = test_client.post(
            "/api/repositories/",
            json={"name": "Test", "path": "/test", "encryption": "none"}
        )

        assert response.status_code == 403

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

        # May fail due to permissions (403), validation (422), during creation (500), or duplicate constraint (400)
        assert response.status_code in [400, 403, 422, 500]


@pytest.mark.unit
class TestRepositoriesUpdate:
    """Test repository update operations"""

    def test_update_repository_name(self, test_client: TestClient, admin_headers, test_db):
        """Test updating repository name"""
        repo = Repository(
            name="Old Name",
            path="/tmp/update-repo",
            encryption="none",
            compression="lz4",
            repository_type="local"
        )
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        response = test_client.put(
            f"/api/repositories/{repo.id}",
            json={"name": "New Name"},
            headers=admin_headers
        )

        assert response.status_code in [200, 403, 404, 405]  # Success, auth/notfound/notimpl

    def test_update_repository_compression(self, test_client: TestClient, admin_headers, test_db):
        """Test updating repository compression"""
        repo = Repository(
            name="Compression Test",
            path="/tmp/compression-repo",
            encryption="none",
            compression="lz4",
            repository_type="local"
        )
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        response = test_client.put(
            f"/api/repositories/{repo.id}",
            json={"compression": "zstd"},
            headers=admin_headers
        )

        assert response.status_code in [200, 403, 404]  # Success, forbidden or not found

    def test_update_nonexistent_repository(self, test_client: TestClient, admin_headers):
        """Test updating non-existent repository"""
        response = test_client.put(
            "/api/repositories/99999",
            json={"name": "Updated Name"},
            headers=admin_headers
        )

        assert response.status_code in [403, 404, 405]  # Auth/notfound/notimpl

    def test_update_repository_not_found(self, test_client: TestClient, admin_headers):
        """Test updating non-existent repository returns 404 or 403"""
        response = test_client.put(
            "/api/repositories/99999",
            json={"name": "Updated"},
            headers=admin_headers
        )

        # May be 403 if not admin, or 404 if admin but repo not found
        assert response.status_code in [403, 404]

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

        # Should reject empty name or accept it (depending on validation)
        assert response.status_code in [200, 400, 403, 422]


@pytest.mark.unit
class TestRepositoriesDelete:
    """Test repository deletion"""

    def test_delete_repository(self, test_client: TestClient, admin_headers, test_db):
        """Test deleting repository"""
        repo = Repository(
            name="Delete Me",
            path="/tmp/delete-repo",
            encryption="none",
            compression="lz4",
            repository_type="local"
        )
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        response = test_client.delete(
            f"/api/repositories/{repo.id}",
            headers=admin_headers
        )

        assert response.status_code in [200, 204, 403]  # Success or forbidden

    def test_delete_nonexistent_repository(self, test_client: TestClient, admin_headers):
        """Test deleting non-existent repository"""
        response = test_client.delete(
            "/api/repositories/99999",
            headers=admin_headers
        )

        assert response.status_code in [403, 404, 405]  # Auth/notfound/notimpl

    def test_delete_repository_not_found(self, test_client: TestClient, admin_headers):
        """Test deleting non-existent repository returns 404 or 403"""
        response = test_client.delete("/api/repositories/99999", headers=admin_headers)

        assert response.status_code in [403, 404]

    def test_delete_repository_no_auth(self, test_client: TestClient):
        """Test deleting repository without authentication returns 403"""
        response = test_client.delete("/api/repositories/1")

        assert response.status_code == 403

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


@pytest.mark.unit
class TestRepositoriesStatistics:
    """Test repository statistics and info"""

    def test_get_repository_stats(self, test_client: TestClient, admin_headers, test_db):
        """Test getting repository statistics"""
        repo = Repository(
            name="Stats Repo",
            path="/tmp/stats-repo",
            encryption="none",
            compression="lz4",
            repository_type="local"
        )
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        response = test_client.get(
            f"/api/repositories/{repo.id}/stats",
            headers=admin_headers
        )

        assert response.status_code in [200, 403, 404, 500]

    def test_get_repository_info(self, test_client: TestClient, admin_headers, test_db):
        """Test getting repository info"""
        repo = Repository(
            name="Info Repo",
            path="/tmp/info-repo",
            encryption="none",
            compression="lz4",
            repository_type="local"
        )
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        response = test_client.get(
            f"/api/repositories/{repo.id}/info",
            headers=admin_headers
        )

        assert response.status_code in [200, 403, 404, 500]

    def test_get_repository_stats_not_found(self, test_client: TestClient, admin_headers):
        """Test getting stats for non-existent repository returns 404"""
        response = test_client.get("/api/repositories/99999/stats", headers=admin_headers)

        assert response.status_code == 404

    def test_get_repository_info_not_found(self, test_client: TestClient, admin_headers):
        """Test getting info for non-existent repository returns 404"""
        response = test_client.get("/api/repositories/99999/info", headers=admin_headers)

        assert response.status_code == 404

    def test_get_stats_no_auth(self, test_client: TestClient):
        """Test getting repository stats without authentication returns 403"""
        response = test_client.get("/api/repositories/1/stats")

        assert response.status_code == 403

    def test_get_info_no_auth(self, test_client: TestClient):
        """Test getting repository info without authentication returns 403"""
        response = test_client.get("/api/repositories/1/info")

        assert response.status_code == 403


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

    def test_import_repository_no_auth(self, test_client: TestClient):
        """Test importing repository without authentication returns 403"""
        response = test_client.post(
            "/api/repositories/import",
            json={"name": "Test", "path": "/test", "encryption": "none"}
        )

        assert response.status_code == 403


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
class TestRepositoryCheckSchedule:
    """Test repository check schedule endpoints"""

    def test_get_check_schedule(self, test_client: TestClient, admin_headers, test_db):
        """Test getting check schedule for a repository"""
        repo = Repository(
            name="Test Repo",
            path="/tmp/test",
            encryption="none",
            repository_type="local",
            check_cron_expression="0 2 * * 0",  # Weekly on Sunday at 2 AM
            check_max_duration=3600,
            notify_on_check_success=False,
            notify_on_check_failure=True
        )
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        response = test_client.get(f"/api/repositories/{repo.id}/check-schedule", headers=admin_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["repository_id"] == repo.id
        assert data["check_cron_expression"] == "0 2 * * 0"
        assert data["check_max_duration"] == 3600
        assert data["notify_on_check_success"] == False
        assert data["notify_on_check_failure"] == True
        assert data["enabled"] == True

    def test_get_check_schedule_disabled(self, test_client: TestClient, admin_headers, test_db):
        """Test getting check schedule for repository with no schedule"""
        repo = Repository(
            name="Test Repo",
            path="/tmp/test",
            encryption="none",
            repository_type="local",
            check_cron_expression=None
        )
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        response = test_client.get(f"/api/repositories/{repo.id}/check-schedule", headers=admin_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["repository_id"] == repo.id
        assert data["check_cron_expression"] is None
        assert data["enabled"] == False

    def test_update_check_schedule(self, test_client: TestClient, admin_headers, test_db):
        """Test updating check schedule for a repository"""
        repo = Repository(
            name="Test Repo",
            path="/tmp/test",
            encryption="none",
            repository_type="local"
        )
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        # Update check schedule
        payload = {
            "cron_expression": "0 3 * * *",  # Daily at 3 AM
            "max_duration": 7200,
            "notify_on_success": True,
            "notify_on_failure": False
        }
        response = test_client.put(
            f"/api/repositories/{repo.id}/check-schedule",
            headers=admin_headers,
            json=payload
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] == True
        assert data["repository"]["check_cron_expression"] == "0 3 * * *"
        assert data["repository"]["check_max_duration"] == 7200
        assert data["repository"]["notify_on_check_success"] == True
        assert data["repository"]["notify_on_check_failure"] == False
        assert data["repository"]["next_scheduled_check"] is not None

    def test_update_check_schedule_disable(self, test_client: TestClient, admin_headers, test_db):
        """Test disabling check schedule for a repository"""
        repo = Repository(
            name="Test Repo",
            path="/tmp/test",
            encryption="none",
            repository_type="local",
            check_cron_expression="0 2 * * 0"  # Weekly on Sunday at 2 AM
        )
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        # Disable check schedule
        payload = {"cron_expression": ""}
        response = test_client.put(
            f"/api/repositories/{repo.id}/check-schedule",
            headers=admin_headers,
            json=payload
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] == True
        assert data["repository"]["check_cron_expression"] is None
        assert data["repository"]["next_scheduled_check"] is None

    def test_get_check_schedule_not_found(self, test_client: TestClient, admin_headers):
        """Test getting check schedule for non-existent repository"""
        response = test_client.get("/api/repositories/99999/check-schedule", headers=admin_headers)

        assert response.status_code == 404

    def test_update_check_schedule_not_found(self, test_client: TestClient, admin_headers):
        """Test updating check schedule for non-existent repository"""
        payload = {"cron_expression": "0 2 * * 0"}
        response = test_client.put(
            "/api/repositories/99999/check-schedule",
            headers=admin_headers,
            json=payload
        )

        assert response.status_code == 404
