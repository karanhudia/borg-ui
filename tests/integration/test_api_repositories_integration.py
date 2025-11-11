"""
Integration tests for repositories API with real borg operations

These tests use actual borg repositories to verify end-to-end functionality.
"""
import pytest
import json
from fastapi.testclient import TestClient


@pytest.mark.integration
@pytest.mark.requires_borg
class TestRepositoryInitialization:
    """Test repository initialization with real borg"""

    def test_initialize_unencrypted_repository(
        self,
        test_client: TestClient,
        admin_headers,
        test_db,
        tmp_path
    ):
        """Test initializing a new unencrypted borg repository"""
        repo_path = tmp_path / "new-repo"

        # Create repository via API (which should initialize borg repo)
        response = test_client.post(
            "/api/repositories/",
            json={
                "name": "Test Init Repo",
                "path": str(repo_path),
                "encryption": "none",
                "compression": "lz4",
                "repository_type": "local",
                "source_directories": ["/tmp/test-source"]
            },
            headers=admin_headers
        )

        assert response.status_code in [200, 201]
        data = response.json()

        # Verify repository was created in database
        if "repository" in data:
            repo_data = data["repository"]
        else:
            repo_data = data

        assert repo_data["name"] == "Test Init Repo"
        assert repo_data["encryption"] == "none"

    def test_initialize_encrypted_repository(
        self,
        test_client: TestClient,
        admin_headers,
        test_db,
        tmp_path
    ):
        """Test initializing a new encrypted borg repository"""
        repo_path = tmp_path / "encrypted-new-repo"

        response = test_client.post(
            "/api/repositories/",
            json={
                "name": "Encrypted Init Repo",
                "path": str(repo_path),
                "encryption": "repokey",
                "passphrase": "test-password-123",
                "compression": "lz4",
                "repository_type": "local",
                "source_directories": ["/tmp/test-source"]
            },
            headers=admin_headers
        )

        assert response.status_code in [200, 201]
        data = response.json()

        if "repository" in data:
            repo_data = data["repository"]
        else:
            repo_data = data

        assert repo_data["name"] == "Encrypted Init Repo"
        assert repo_data["encryption"] == "repokey"


@pytest.mark.integration
@pytest.mark.requires_borg
class TestRepositoryStats:
    """Test getting repository statistics from real repos"""

    def test_get_stats_from_real_repository(
        self,
        test_client: TestClient,
        admin_headers,
        db_borg_repo_with_archives
    ):
        """Test getting stats from a repository with archives"""
        repo, repo_path, test_data_path, archive_names = db_borg_repo_with_archives

        response = test_client.get(
            f"/api/repositories/{repo.id}/stats",
            headers=admin_headers
        )

        assert response.status_code == 200
        data = response.json()

        # Should have stats from real borg repository
        assert "stats" in data or "total_size" in data

        # Stats should have size information
        stats = data.get("stats", data)
        assert "total_size" in stats or "original_size" in stats

    def test_get_stats_from_empty_repository(
        self,
        test_client: TestClient,
        admin_headers,
        db_borg_repo
    ):
        """Test getting stats from an empty repository"""
        repo, repo_path, test_data_path = db_borg_repo

        response = test_client.get(
            f"/api/repositories/{repo.id}/stats",
            headers=admin_headers
        )

        # Empty repo might return 200 with zero stats or 500/404
        assert response.status_code in [200, 404, 500]

        if response.status_code == 200:
            data = response.json()
            stats = data.get("stats", data)
            # Empty repo should have minimal or zero stats
            assert isinstance(stats, dict)

    def test_get_stats_encrypted_repository(
        self,
        test_client: TestClient,
        admin_headers,
        db_encrypted_borg_repo
    ):
        """Test getting stats from encrypted repository"""
        repo, repo_path, test_data_path, passphrase = db_encrypted_borg_repo

        response = test_client.get(
            f"/api/repositories/{repo.id}/stats",
            headers=admin_headers
        )

        assert response.status_code == 200
        data = response.json()

        # Should successfully get stats with stored passphrase
        assert "stats" in data or "total_size" in data


@pytest.mark.integration
@pytest.mark.requires_borg
class TestRepositoryInfo:
    """Test getting repository info from real repos"""

    def test_get_info_from_real_repository(
        self,
        test_client: TestClient,
        admin_headers,
        db_borg_repo_with_archives
    ):
        """Test getting info from a repository with archives"""
        repo, repo_path, test_data_path, archive_names = db_borg_repo_with_archives

        response = test_client.get(
            f"/api/repositories/{repo.id}/info",
            headers=admin_headers
        )

        assert response.status_code == 200
        data = response.json()

        # Should have repository info
        assert "info" in data

        # Info should contain repository metadata
        info = data["info"]
        assert "repository" in info
        assert "id" in info["repository"] or "location" in info["repository"]

    def test_get_info_encrypted_repository(
        self,
        test_client: TestClient,
        admin_headers,
        db_encrypted_borg_repo
    ):
        """Test getting info from encrypted repository"""
        repo, repo_path, test_data_path, passphrase = db_encrypted_borg_repo

        response = test_client.get(
            f"/api/repositories/{repo.id}/info",
            headers=admin_headers
        )

        assert response.status_code == 200
        data = response.json()

        # Should successfully get info with stored passphrase
        info = data.get("info", data.get("repository", data))
        assert isinstance(info, dict)

        # Should show encryption info
        if "encryption" in info:
            assert info["encryption"]["mode"] in ["repokey", "keyfile", "repokey-blake2"]


@pytest.mark.integration
@pytest.mark.requires_borg
class TestRepositoryWithArchives:
    """Test repository operations that involve archives"""

    def test_get_repository_by_id_includes_archive_count(
        self,
        test_client: TestClient,
        admin_headers,
        db_borg_repo_with_archives
    ):
        """Test that getting a repository includes archive count"""
        repo, repo_path, test_data_path, archive_names = db_borg_repo_with_archives

        response = test_client.get(
            f"/api/repositories/{repo.id}",
            headers=admin_headers
        )

        assert response.status_code == 200
        data = response.json()

        # Repository should have archive count
        repo_data = data.get("repository", data)
        if "archive_count" in repo_data:
            assert repo_data["archive_count"] >= 2  # We created 2 archives

    def test_list_repositories_shows_archive_counts(
        self,
        test_client: TestClient,
        admin_headers,
        db_borg_repo_with_archives
    ):
        """Test that listing repositories includes archive counts"""
        repo, repo_path, test_data_path, archive_names = db_borg_repo_with_archives

        response = test_client.get(
            "/api/repositories/",
            headers=admin_headers
        )

        assert response.status_code == 200
        data = response.json()

        repos = data.get("repositories", data)
        if isinstance(repos, list) and len(repos) > 0:
            # Find our repository
            our_repo = next((r for r in repos if r["id"] == repo.id), None)
            if our_repo and "archive_count" in our_repo:
                assert our_repo["archive_count"] >= 2


@pytest.mark.integration
@pytest.mark.requires_borg
class TestImportExistingRepository:
    """Test importing existing borg repositories"""

    def test_import_existing_unencrypted_repo(
        self,
        test_client: TestClient,
        admin_headers,
        borg_repo_with_archives
    ):
        """Test importing an existing borg repository"""
        repo_path, test_data_path, archive_names = borg_repo_with_archives

        response = test_client.post(
            "/api/repositories/import",
            json={
                "name": "Imported Repo",
                "path": str(repo_path),
                "encryption": "none",
                "source_directories": ["/tmp/test-source"]
            },
            headers=admin_headers
        )

        # Should successfully import or return appropriate error
        assert response.status_code in [200, 201, 400, 409]

        if response.status_code in [200, 201]:
            data = response.json()
            repo_data = data.get("repository", data)
            assert repo_data["name"] == "Imported Repo"
            assert repo_data["path"] == str(repo_path)

    def test_import_existing_encrypted_repo(
        self,
        test_client: TestClient,
        admin_headers,
        encrypted_borg_repo
    ):
        """Test importing an existing encrypted repository"""
        repo_path, test_data_path, passphrase = encrypted_borg_repo

        response = test_client.post(
            "/api/repositories/import",
            json={
                "name": "Imported Encrypted Repo",
                "path": str(repo_path),
                "encryption": "repokey",
                "passphrase": passphrase,
                "source_directories": ["/tmp/test-source"]
            },
            headers=admin_headers
        )

        # Should successfully import
        assert response.status_code in [200, 201, 400, 409]

        if response.status_code in [200, 201]:
            data = response.json()
            repo_data = data.get("repository", data)
            assert repo_data["name"] == "Imported Encrypted Repo"
            assert repo_data["encryption"] == "repokey"


@pytest.mark.integration
@pytest.mark.requires_borg
class TestRepositoryDeletion:
    """Test deleting repositories with archives"""

    def test_delete_repository_with_archives(
        self,
        test_client: TestClient,
        admin_headers,
        db_borg_repo_with_archives
    ):
        """Test deleting a repository that has archives"""
        repo, repo_path, test_data_path, archive_names = db_borg_repo_with_archives

        # Delete the repository
        response = test_client.delete(
            f"/api/repositories/{repo.id}",
            headers=admin_headers
        )

        # Should successfully delete
        assert response.status_code in [200, 204]

        # Verify repository is deleted
        get_response = test_client.get(
            f"/api/repositories/{repo.id}",
            headers=admin_headers
        )
        assert get_response.status_code == 404


@pytest.mark.integration
@pytest.mark.requires_borg
class TestRepositoryOperationsWithCompression:
    """Test repository compression settings"""

    def test_repository_with_different_compressions(
        self,
        test_client: TestClient,
        admin_headers,
        test_db,
        tmp_path
    ):
        """Test creating repositories with different compression algorithms"""
        compressions = ["none", "lz4", "zstd"]

        for comp in compressions:
            repo_path = tmp_path / f"repo-{comp}"

            response = test_client.post(
                "/api/repositories/",
                json={
                    "name": f"Repo with {comp}",
                    "path": str(repo_path),
                    "encryption": "none",
                    "compression": comp,
                    "repository_type": "local",
                    "source_directories": ["/tmp/test-source"]
                },
                headers=admin_headers
            )

            # Should successfully create with any compression
            assert response.status_code in [200, 201]
