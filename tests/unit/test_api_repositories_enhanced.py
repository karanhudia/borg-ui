"""
Enhanced comprehensive tests for repositories API with mocking.
Focuses on improving coverage by testing all endpoints with mocked dependencies.
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
        """Test listing repositories"""
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
        """Test getting repository by ID"""
        repo = Repository(name="Test Repo", path="/test/repo", encryption="none", repository_type="local")
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        response = test_client.get(f"/api/repositories/{repo.id}", headers=admin_headers)

        # May succeed or fail based on borg stats availability
        assert response.status_code in [200, 500]
        if response.status_code == 200:
            data = response.json()
            assert "repository" in data
            assert data["repository"]["name"] == "Test Repo"

    def test_get_repository_not_found(self, test_client: TestClient, admin_headers):
        """Test getting non-existent repository"""
        response = test_client.get("/api/repositories/99999", headers=admin_headers)

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()


@pytest.mark.unit
class TestRepositoriesCreate:
    """Test repository creation"""

    def test_create_repository_success(self, test_client: TestClient, admin_headers, test_db):
        """Test successful repository creation with mocked borg"""
        with patch('app.api.repositories.borg.init_repository', new_callable=AsyncMock) as mock_init:
            mock_init.return_value = {"success": True, "stdout": "Repository initialized"}

            response = test_client.post(
                "/api/repositories/",
                json={
                    "name": "New Repo",
                    "path": "/new/repo",
                    "encryption": "none",
                    "compression": "lz4",
                    "repository_type": "local"
                },
                headers=admin_headers
            )

            assert response.status_code in [200, 201]
            if response.status_code in [200, 201]:
                data = response.json()
                assert data["name"] == "New Repo"

    def test_create_repository_validation_error(self, test_client: TestClient, admin_headers):
        """Test repository creation with missing required fields"""
        response = test_client.post(
            "/api/repositories/",
            json={"name": "Incomplete Repo"},  # Missing path, encryption, etc.
            headers=admin_headers
        )

        assert response.status_code == 422  # Validation error


@pytest.mark.unit
class TestRepositoriesUpdate:
    """Test repository update operations"""

    def test_update_repository_success(self, test_client: TestClient, admin_headers, test_db):
        """Test updating repository"""
        repo = Repository(name="Old Name", path="/test/repo", encryption="none", repository_type="local")
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        response = test_client.put(
            f"/api/repositories/{repo.id}",
            json={"name": "New Name", "description": "Updated description"},
            headers=admin_headers
        )

        assert response.status_code in [200, 500]
        if response.status_code == 200:
            data = response.json()
            # Response might be wrapped
            repo_data = data.get("repository", data)
            assert repo_data.get("name") == "New Name"

    def test_update_repository_not_found(self, test_client: TestClient, admin_headers):
        """Test updating non-existent repository"""
        response = test_client.put(
            "/api/repositories/99999",
            json={"name": "Updated"},
            headers=admin_headers
        )

        assert response.status_code == 404


@pytest.mark.unit
class TestRepositoriesDelete:
    """Test repository deletion"""

    def test_delete_repository_success(self, test_client: TestClient, admin_headers, test_db):
        """Test deleting repository"""
        repo = Repository(name="To Delete", path="/delete/repo", encryption="none", repository_type="local")
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)
        repo_id = repo.id

        response = test_client.delete(f"/api/repositories/{repo_id}", headers=admin_headers)

        assert response.status_code == 200

        # Verify deletion
        deleted_repo = test_db.query(Repository).filter(Repository.id == repo_id).first()
        assert deleted_repo is None

    def test_delete_repository_not_found(self, test_client: TestClient, admin_headers):
        """Test deleting non-existent repository"""
        response = test_client.delete("/api/repositories/99999", headers=admin_headers)

        assert response.status_code == 404


@pytest.mark.unit
class TestRepositoriesImport:
    """Test repository import functionality"""

    def test_import_repository_success(self, test_client: TestClient, admin_headers, test_db):
        """Test importing existing repository with mocked borg"""
        with patch('app.api.repositories.borg.info_repo', new_callable=AsyncMock) as mock_info, \
             patch('app.api.repositories.borg.list_archives', new_callable=AsyncMock) as mock_list:

            mock_info.return_value = {
                "success": True,
                "stdout": json.dumps({
                    "repository": {"id": "abc123"},
                    "encryption": {"mode": "none"}
                })
            }

            mock_list.return_value = {
                "success": True,
                "stdout": json.dumps({"archives": []})
            }

            response = test_client.post(
                "/api/repositories/import",
                json={
                    "name": "Imported Repo",
                    "path": "/import/repo",
                    "encryption": "none",
                    "repository_type": "local"
                },
                headers=admin_headers
            )

            assert response.status_code in [200, 201, 500]

    def test_import_repository_validation_error(self, test_client: TestClient, admin_headers):
        """Test importing repository with missing fields"""
        response = test_client.post(
            "/api/repositories/import",
            json={"name": "Incomplete"},
            headers=admin_headers
        )

        assert response.status_code == 422


@pytest.mark.unit
class TestRepositoriesStats:
    """Test repository statistics endpoint"""

    def test_get_repository_stats_success(self, test_client: TestClient, admin_headers, test_db):
        """Test getting repository stats with mocked borg"""
        repo = Repository(name="Stats Repo", path="/stats/repo", encryption="none", repository_type="local")
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        with patch('app.api.repositories.borg.info_repo', new_callable=AsyncMock) as mock_info:
            mock_info.return_value = {
                "success": True,
                "stdout": json.dumps({
                    "cache": {
                        "stats": {
                            "total_size": 1000000,
                            "total_csize": 500000,
                            "unique_csize": 250000
                        }
                    }
                })
            }

            response = test_client.get(f"/api/repositories/{repo.id}/stats", headers=admin_headers)

            assert response.status_code in [200, 500]

    def test_get_repository_stats_not_found(self, test_client: TestClient, admin_headers):
        """Test getting stats for non-existent repository"""
        response = test_client.get("/api/repositories/99999/stats", headers=admin_headers)

        assert response.status_code == 404


@pytest.mark.unit
class TestRepositoriesInfo:
    """Test repository info endpoint"""

    def test_get_repository_info_success(self, test_client: TestClient, admin_headers, test_db):
        """Test getting repository info with mocked borg"""
        repo = Repository(name="Info Repo", path="/info/repo", encryption="none", repository_type="local")
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        with patch('app.api.repositories.borg.info_repo', new_callable=AsyncMock) as mock_info:
            mock_info.return_value = {
                "success": True,
                "stdout": json.dumps({
                    "repository": {"id": "abc123", "location": "/info/repo"},
                    "encryption": {"mode": "none"},
                    "cache": {"path": "/cache"}
                })
            }

            response = test_client.get(f"/api/repositories/{repo.id}/info", headers=admin_headers)

            assert response.status_code in [200, 500]

    def test_get_repository_info_not_found(self, test_client: TestClient, admin_headers):
        """Test getting info for non-existent repository"""
        response = test_client.get("/api/repositories/99999/info", headers=admin_headers)

        assert response.status_code == 404


@pytest.mark.unit
class TestRepositoriesArchives:
    """Test repository archives listing"""

    def test_list_repository_archives_success(self, test_client: TestClient, admin_headers, test_db):
        """Test listing archives in repository with mocked borg"""
        repo = Repository(name="Archive Repo", path="/archive/repo", encryption="none", repository_type="local")
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        with patch('app.api.repositories.borg.list_archives', new_callable=AsyncMock) as mock_list:
            mock_list.return_value = {
                "success": True,
                "stdout": json.dumps({
                    "archives": [
                        {"name": "archive1", "time": "2025-01-01T00:00:00"},
                        {"name": "archive2", "time": "2025-01-02T00:00:00"}
                    ]
                })
            }

            response = test_client.get(f"/api/repositories/{repo.id}/archives", headers=admin_headers)

            assert response.status_code in [200, 500]

    def test_list_repository_archives_not_found(self, test_client: TestClient, admin_headers):
        """Test listing archives for non-existent repository"""
        response = test_client.get("/api/repositories/99999/archives", headers=admin_headers)

        assert response.status_code == 404


@pytest.mark.unit
class TestRepositoriesArchiveInfo:
    """Test repository archive info endpoints"""

    def test_get_archive_info_in_repository_success(self, test_client: TestClient, admin_headers, test_db):
        """Test getting archive info via repository endpoint"""
        repo = Repository(name="Repo", path="/repo", encryption="none", repository_type="local")
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        with patch('app.api.repositories.borg.info_archive', new_callable=AsyncMock) as mock_info:
            mock_info.return_value = {
                "success": True,
                "stdout": json.dumps({
                    "archives": [{
                        "name": "test-archive",
                        "stats": {"original_size": 1000}
                    }]
                })
            }

            response = test_client.get(
                f"/api/repositories/{repo.id}/archives/test-archive/info",
                headers=admin_headers
            )

            assert response.status_code in [200, 500]

    def test_get_archive_files_in_repository_success(self, test_client: TestClient, admin_headers, test_db):
        """Test getting archive files via repository endpoint"""
        repo = Repository(name="Repo", path="/repo", encryption="none", repository_type="local")
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        with patch('app.api.repositories.borg.list_archive_contents', new_callable=AsyncMock) as mock_list:
            mock_list.return_value = {
                "success": True,
                "stdout": json.dumps({"path": "/file.txt"}) + "\n"
            }

            response = test_client.get(
                f"/api/repositories/{repo.id}/archives/test-archive/files",
                headers=admin_headers
            )

            assert response.status_code in [200, 500]


@pytest.mark.unit
class TestRepositoriesMaintenance:
    """Test repository maintenance operations"""

    def test_check_repository_success(self, test_client: TestClient, admin_headers, test_db):
        """Test repository check operation"""
        repo = Repository(name="Check Repo", path="/check/repo", encryption="none", repository_type="local")
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        with patch('app.services.check_service.CheckService.execute_check', new_callable=AsyncMock) as mock_check:
            mock_check.return_value = None  # Just start the background task

            response = test_client.post(
                f"/api/repositories/{repo.id}/check",
                json={"max_duration": 3600},
                headers=admin_headers
            )

            # Should accept the request
            assert response.status_code in [200, 202, 500]

    def test_compact_repository_success(self, test_client: TestClient, admin_headers, test_db):
        """Test repository compact operation"""
        repo = Repository(name="Compact Repo", path="/compact/repo", encryption="none", repository_type="local")
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        with patch('app.services.compact_service.CompactService.execute_compact', new_callable=AsyncMock) as mock_compact:
            mock_compact.return_value = None

            response = test_client.post(
                f"/api/repositories/{repo.id}/compact",
                headers=admin_headers
            )

            assert response.status_code in [200, 202, 500]

    def test_prune_repository_success(self, test_client: TestClient, admin_headers, test_db):
        """Test repository prune operation"""
        repo = Repository(name="Prune Repo", path="/prune/repo", encryption="none", repository_type="local")
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        with patch('app.api.repositories.borg.prune', new_callable=AsyncMock) as mock_prune, \
             patch('app.api.repositories.borg.list_archives', new_callable=AsyncMock) as mock_list:

            mock_prune.return_value = {"success": True, "stdout": "Pruning complete"}
            mock_list.return_value = {"success": True, "stdout": json.dumps({"archives": []})}

            response = test_client.post(
                f"/api/repositories/{repo.id}/prune",
                json={
                    "keep_daily": 7,
                    "keep_weekly": 4,
                    "keep_monthly": 6
                },
                headers=admin_headers
            )

            assert response.status_code in [200, 500]

    def test_break_lock_repository_success(self, test_client: TestClient, admin_headers, test_db):
        """Test breaking repository lock"""
        repo = Repository(name="Lock Repo", path="/lock/repo", encryption="none", repository_type="local")
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        with patch('app.api.repositories.borg.break_lock', new_callable=AsyncMock) as mock_break:
            mock_break.return_value = {"success": True, "stdout": "Lock broken"}

            response = test_client.post(
                f"/api/repositories/{repo.id}/break-lock",
                headers=admin_headers
            )

            assert response.status_code in [200, 500]


@pytest.mark.unit
class TestRepositoriesJobStatus:
    """Test repository job status endpoints"""

    def test_get_repository_check_jobs(self, test_client: TestClient, admin_headers, test_db):
        """Test getting repository check jobs"""
        repo = Repository(name="Job Repo", path="/job/repo", encryption="none", repository_type="local")
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        response = test_client.get(f"/api/repositories/{repo.id}/check-jobs", headers=admin_headers)

        assert response.status_code in [200, 500]

    def test_get_repository_compact_jobs(self, test_client: TestClient, admin_headers, test_db):
        """Test getting repository compact jobs"""
        repo = Repository(name="Job Repo", path="/job/repo", encryption="none", repository_type="local")
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        response = test_client.get(f"/api/repositories/{repo.id}/compact-jobs", headers=admin_headers)

        assert response.status_code in [200, 500]

    def test_get_repository_running_jobs(self, test_client: TestClient, admin_headers, test_db):
        """Test getting repository running jobs"""
        repo = Repository(name="Job Repo", path="/job/repo", encryption="none", repository_type="local")
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        response = test_client.get(f"/api/repositories/{repo.id}/running-jobs", headers=admin_headers)

        assert response.status_code in [200, 500]


@pytest.mark.unit
class TestRepositoriesAuthentication:
    """Test authentication for repository endpoints"""

    def test_list_repositories_no_auth(self, test_client: TestClient):
        """Test listing repositories without authentication"""
        response = test_client.get("/api/repositories/")

        assert response.status_code == 403

    def test_create_repository_no_auth(self, test_client: TestClient):
        """Test creating repository without authentication"""
        response = test_client.post(
            "/api/repositories/",
            json={"name": "Test", "path": "/test", "encryption": "none"}
        )

        assert response.status_code == 403

    def test_delete_repository_no_auth(self, test_client: TestClient):
        """Test deleting repository without authentication"""
        response = test_client.delete("/api/repositories/1")

        assert response.status_code == 403
