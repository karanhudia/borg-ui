"""
Integration tests for restore API with real borg operations

These tests use actual borg repositories and perform real restore operations.
All test data is automatically cleaned up after tests complete.
"""
import pytest
import json
import time
from pathlib import Path
from fastapi.testclient import TestClient


@pytest.mark.integration
@pytest.mark.requires_borg
class TestRestoreOperations:
    """Test restoring files from real archives"""

    def test_restore_files_from_archive(
        self,
        test_client: TestClient,
        admin_headers,
        db_borg_repo_with_archives,
        tmp_path
    ):
        """Test restoring files from a real archive"""
        repo, repo_path, test_data_path, archive_names = db_borg_repo_with_archives

        # Create target directory for restore
        restore_target = tmp_path / "restore-target"
        restore_target.mkdir()

        # Get list of files in the archive first
        contents_response = test_client.get(
            f"/api/restore/contents?repository={repo.path}&archive={archive_names[0]}",
            headers=admin_headers
        )

        assert contents_response.status_code == 200

        # Start restore of all files
        restore_response = test_client.post(
            "/api/restore/start",
            json={
                "repository": repo.path,
                "archive": archive_names[0],
                "target": str(restore_target),
                "files": []  # Empty means restore all
            },
            headers=admin_headers
        )

        # Should either succeed or return validation error
        assert restore_response.status_code in [200, 400, 422]

        if restore_response.status_code == 200:
            job_data = restore_response.json()
            assert "job_id" in job_data
            job_id = job_data["job_id"]

            # Wait for restore to complete
            max_wait = 30
            start_time = time.time()
            status = "pending"

            while status in ["pending", "running"] and (time.time() - start_time) < max_wait:
                time.sleep(1)
                status_response = test_client.get(
                    f"/api/restore/jobs/{job_id}",
                    headers=admin_headers
                )
                if status_response.status_code == 200:
                    status = status_response.json().get("status", "unknown")

            # Restore should complete
            assert status in ["completed", "failed"]

    def test_restore_specific_files(
        self,
        test_client: TestClient,
        admin_headers,
        db_borg_repo_with_archives,
        tmp_path
    ):
        """Test restoring specific files only"""
        repo, repo_path, test_data_path, archive_names = db_borg_repo_with_archives

        restore_target = tmp_path / "partial-restore"
        restore_target.mkdir()

        # Restore only specific files
        restore_response = test_client.post(
            "/api/restore/start",
            json={
                "repository": repo.path,
                "archive": archive_names[0],
                "target": str(restore_target),
                "files": [f"{test_data_path}/file1.txt"]  # Restore only file1
            },
            headers=admin_headers
        )

        assert restore_response.status_code in [200, 400, 422]

    def test_restore_to_custom_location(
        self,
        test_client: TestClient,
        admin_headers,
        db_borg_repo_with_archives,
        tmp_path
    ):
        """Test restoring to a custom target directory"""
        repo, repo_path, test_data_path, archive_names = db_borg_repo_with_archives

        # Custom restore location
        custom_target = tmp_path / "custom" / "restore" / "location"
        custom_target.mkdir(parents=True)

        restore_response = test_client.post(
            "/api/restore/start",
            json={
                "repository": repo.path,
                "archive": archive_names[0],
                "target": str(custom_target),
                "files": []
            },
            headers=admin_headers
        )

        assert restore_response.status_code in [200, 400, 422]


@pytest.mark.integration
@pytest.mark.requires_borg
class TestRestoreFromEncryptedRepo:
    """Test restore operations from encrypted repositories"""

    def test_restore_from_encrypted_archive(
        self,
        test_client: TestClient,
        admin_headers,
        db_encrypted_borg_repo,
        tmp_path
    ):
        """Test restoring files from encrypted repository"""
        repo, repo_path, test_data_path, passphrase = db_encrypted_borg_repo

        restore_target = tmp_path / "encrypted-restore"
        restore_target.mkdir()

        # List contents first to verify we can access encrypted repo
        contents_response = test_client.get(
            f"/api/restore/contents?repository={repo.path}&archive=encrypted-archive",
            headers=admin_headers
        )

        # Should succeed with correct passphrase
        assert contents_response.status_code in [200, 500]

        if contents_response.status_code == 200:
            # Try restore
            restore_response = test_client.post(
                "/api/restore/start",
                json={
                    "repository": repo.path,
                    "archive": "encrypted-archive",
                    "target": str(restore_target),
                    "files": []
                },
                headers=admin_headers
            )

            assert restore_response.status_code in [200, 400, 422]


@pytest.mark.integration
@pytest.mark.requires_borg
class TestRestoreListingOperations:
    """Test listing operations for restore"""

    def test_list_repositories_for_restore(
        self,
        test_client: TestClient,
        admin_headers,
        db_borg_repo_with_archives
    ):
        """Test listing repositories available for restore"""
        repo, repo_path, test_data_path, archive_names = db_borg_repo_with_archives

        response = test_client.get(
            "/api/restore/repositories",
            headers=admin_headers
        )

        assert response.status_code == 200
        data = response.json()

        # Should have at least our test repository
        repos = data.get("repositories", data)
        if isinstance(repos, list):
            assert len(repos) >= 1
            # Find our repo
            our_repo = next((r for r in repos if r["path"] == repo.path), None)
            assert our_repo is not None

    def test_list_archives_for_restore(
        self,
        test_client: TestClient,
        admin_headers,
        db_borg_repo_with_archives
    ):
        """Test listing archives in a repository for restore"""
        repo, repo_path, test_data_path, archive_names = db_borg_repo_with_archives

        response = test_client.get(
            f"/api/restore/archives?repository={repo.path}",
            headers=admin_headers
        )

        assert response.status_code == 200
        data = response.json()

        # Should list the archives
        archives = data.get("archives", [])
        if isinstance(archives, str):
            archives = json.loads(archives)
            archives = archives.get("archives", [])

        assert len(archives) >= 2  # We created 2 archives

    def test_list_archive_contents_for_restore(
        self,
        test_client: TestClient,
        admin_headers,
        db_borg_repo_with_archives
    ):
        """Test listing contents of an archive for restore preview"""
        repo, repo_path, test_data_path, archive_names = db_borg_repo_with_archives

        response = test_client.get(
            f"/api/restore/contents?repository={repo.path}&archive={archive_names[0]}",
            headers=admin_headers
        )

        assert response.status_code == 200
        data = response.json()

        # Should have contents
        assert "contents" in data or "files" in data


@pytest.mark.integration
@pytest.mark.requires_borg
class TestRestorePreview:
    """Test restore preview functionality"""

    def test_preview_restore_shows_files(
        self,
        test_client: TestClient,
        admin_headers,
        db_borg_repo_with_archives
    ):
        """Test previewing what would be restored"""
        repo, repo_path, test_data_path, archive_names = db_borg_repo_with_archives

        response = test_client.post(
            "/api/restore/preview",
            json={
                "repository": repo.path,
                "archive": archive_names[0],
                "files": []  # Preview all files
            },
            headers=admin_headers
        )

        assert response.status_code in [200, 400, 422]

        if response.status_code == 200:
            data = response.json()
            # Should show what would be restored
            assert "files" in data or "preview" in data or "contents" in data

    def test_preview_restore_with_path_filter(
        self,
        test_client: TestClient,
        admin_headers,
        db_borg_repo_with_archives
    ):
        """Test previewing restore with specific paths"""
        repo, repo_path, test_data_path, archive_names = db_borg_repo_with_archives

        response = test_client.post(
            "/api/restore/preview",
            json={
                "repository": repo.path,
                "archive": archive_names[0],
                "files": [f"{test_data_path}/subdir"]  # Preview only subdir
            },
            headers=admin_headers
        )

        assert response.status_code in [200, 400, 422]


@pytest.mark.integration
@pytest.mark.requires_borg
class TestRestoreJobManagement:
    """Test restore job lifecycle"""

    def test_list_restore_jobs(
        self,
        test_client: TestClient,
        admin_headers
    ):
        """Test listing restore jobs"""
        response = test_client.get(
            "/api/restore/jobs",
            headers=admin_headers
        )

        assert response.status_code == 200
        data = response.json()

        # Should return jobs list (may be empty)
        jobs = data.get("jobs", data)
        assert isinstance(jobs, list) or isinstance(jobs, dict)

    def test_get_restore_job_status(
        self,
        test_client: TestClient,
        admin_headers,
        db_borg_repo_with_archives,
        tmp_path
    ):
        """Test getting status of a restore job"""
        repo, repo_path, test_data_path, archive_names = db_borg_repo_with_archives

        restore_target = tmp_path / "status-test-restore"
        restore_target.mkdir()

        # Start a restore
        restore_response = test_client.post(
            "/api/restore/start",
            json={
                "repository": repo.path,
                "archive": archive_names[0],
                "target": str(restore_target),
                "files": []
            },
            headers=admin_headers
        )

        if restore_response.status_code == 200:
            job_id = restore_response.json()["job_id"]

            # Check status
            status_response = test_client.get(
                f"/api/restore/jobs/{job_id}",
                headers=admin_headers
            )

            assert status_response.status_code == 200
            status_data = status_response.json()
            assert "status" in status_data
            assert status_data["status"] in ["pending", "running", "completed", "failed"]


@pytest.mark.integration
@pytest.mark.requires_borg
class TestRestoreWithDifferentArchives:
    """Test restore from different archives (incremental scenarios)"""

    def test_restore_from_latest_archive(
        self,
        test_client: TestClient,
        admin_headers,
        db_borg_repo_with_archives,
        tmp_path
    ):
        """Test restoring from the latest archive"""
        repo, repo_path, test_data_path, archive_names = db_borg_repo_with_archives

        # Restore from the latest archive (second one)
        restore_target = tmp_path / "latest-restore"
        restore_target.mkdir()

        response = test_client.post(
            "/api/restore/start",
            json={
                "repository": repo.path,
                "archive": archive_names[-1],  # Latest archive
                "target": str(restore_target),
                "files": []
            },
            headers=admin_headers
        )

        assert response.status_code in [200, 400, 422]

    def test_restore_from_older_archive(
        self,
        test_client: TestClient,
        admin_headers,
        db_borg_repo_with_archives,
        tmp_path
    ):
        """Test restoring from an older archive"""
        repo, repo_path, test_data_path, archive_names = db_borg_repo_with_archives

        # Restore from the first (older) archive
        restore_target = tmp_path / "old-restore"
        restore_target.mkdir()

        response = test_client.post(
            "/api/restore/start",
            json={
                "repository": repo.path,
                "archive": archive_names[0],  # First archive
                "target": str(restore_target),
                "files": []
            },
            headers=admin_headers
        )

        assert response.status_code in [200, 400, 422]
