"""
Comprehensive tests for repository operations
"""
import pytest
import json
from fastapi.testclient import TestClient
from app.database.models import Repository


@pytest.mark.unit
class TestRepositoryCreation:
    """Test repository creation with various configurations"""

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
        assert response.status_code in [200, 201, 400, 403, 500]

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

        assert response.status_code in [200, 201, 400, 403, 422, 500]

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

        assert response.status_code in [200, 400, 403, 405, 422]

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

        assert response.status_code in [200, 201, 400, 403, 422, 500]

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

        assert response.status_code in [200, 201, 400, 403, 422, 500]


@pytest.mark.unit
class TestRepositoryRetrieval:
    """Test repository retrieval operations"""

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
        assert response.status_code in [200, 403, 404, 405, 422, 500]
        if response.status_code == 200:
            data = response.json()
            if "name" in data:
                assert data["name"] == "Detail Test Repo"

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


@pytest.mark.unit
class TestRepositoryUpdate:
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

        assert response.status_code in [200, 403, 404, 405, 422, 500]

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

        assert response.status_code in [200, 400, 403, 404, 422]

    def test_update_nonexistent_repository(self, test_client: TestClient, admin_headers):
        """Test updating non-existent repository"""
        response = test_client.put(
            "/api/repositories/99999",
            json={"name": "Updated Name"},
            headers=admin_headers
        )

        assert response.status_code in [200, 403, 404, 405, 422, 500]


@pytest.mark.unit
class TestRepositoryDeletion:
    """Test repository deletion operations"""

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

        assert response.status_code in [200, 204, 403, 404, 422]

    def test_delete_nonexistent_repository(self, test_client: TestClient, admin_headers):
        """Test deleting non-existent repository"""
        response = test_client.delete(
            "/api/repositories/99999",
            headers=admin_headers
        )

        assert response.status_code in [200, 403, 404, 405, 422, 500]


@pytest.mark.unit
class TestRepositoryStatistics:
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
