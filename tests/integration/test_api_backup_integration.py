"""
Integration tests for backup API with real borg operations

These tests use actual borg repositories and perform real backups with small text files.
All test data is automatically cleaned up after tests complete.
"""
import pytest
import json
import time
from pathlib import Path
from fastapi.testclient import TestClient


@pytest.mark.integration
@pytest.mark.requires_borg
class TestBackupCreation:
    """Test creating backups with real borg operations"""

    def test_backup_creates_real_archive(
        self,
        test_client: TestClient,
        admin_headers,
        db_borg_repo,
        tmp_path
    ):
        """Test that backup actually creates an archive in the repository"""
        repo, repo_path, _ = db_borg_repo

        # Create source directory with test files
        source_dir = tmp_path / "backup-source"
        source_dir.mkdir()
        (source_dir / "test1.txt").write_text("Hello from test file 1")
        (source_dir / "test2.txt").write_text("Hello from test file 2")

        # Update repository to use our test source
        repo.source_directories = json.dumps([str(source_dir)])

        # Start backup
        response = test_client.post(
            "/api/backup/start",
            json={
                "repository": repo.path
            },
            headers=admin_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert "job_id" in data
        job_id = data["job_id"]

        # Wait for backup to complete (with timeout)
        max_wait = 30  # 30 seconds max
        start_time = time.time()
        status = "pending"

        while status in ["pending", "running"] and (time.time() - start_time) < max_wait:
            time.sleep(1)
            status_response = test_client.get(
                f"/api/backup/jobs/{job_id}",
                headers=admin_headers
            )
            if status_response.status_code == 200:
                status_data = status_response.json()
                status = status_data.get("status", "unknown")

        # Verify backup completed successfully
        assert status == "completed", f"Backup did not complete in time. Status: {status}"

        # Verify archive was created by listing archives
        from app.core.borg import BorgInterface
        import asyncio
        borg = BorgInterface()

        async def check_archives():
            result = await borg.list_archives(repo.path)
            return result

        list_result = asyncio.run(check_archives())
        assert list_result["success"]

        archives_data = json.loads(list_result["stdout"])
        archives = archives_data.get("archives", [])
        assert len(archives) >= 1, "No archives found after backup"

    def test_backup_with_multiple_files(
        self,
        test_client: TestClient,
        admin_headers,
        db_borg_repo,
        tmp_path
    ):
        """Test backup with multiple files and subdirectories"""
        repo, repo_path, _ = db_borg_repo

        # Create complex directory structure
        source_dir = tmp_path / "complex-source"
        source_dir.mkdir()

        # Root level files
        (source_dir / "root1.txt").write_text("Root file 1")
        (source_dir / "root2.txt").write_text("Root file 2")

        # Subdirectory with files
        subdir1 = source_dir / "subdir1"
        subdir1.mkdir()
        (subdir1 / "sub1.txt").write_text("Subdirectory file 1")
        (subdir1 / "sub2.txt").write_text("Subdirectory file 2")

        # Nested subdirectory
        subdir2 = subdir1 / "nested"
        subdir2.mkdir()
        (subdir2 / "nested.txt").write_text("Nested file")

        repo.source_directories = json.dumps([str(source_dir)])

        response = test_client.post(
            "/api/backup/start",
            json={"repository": repo.path},
            headers=admin_headers
        )

        assert response.status_code == 200
        job_id = response.json()["job_id"]

        # Wait for completion
        max_wait = 30
        start_time = time.time()
        status = "pending"

        while status in ["pending", "running"] and (time.time() - start_time) < max_wait:
            time.sleep(1)
            status_response = test_client.get(
                f"/api/backup/jobs/{job_id}",
                headers=admin_headers
            )
            if status_response.status_code == 200:
                status = status_response.json().get("status", "unknown")

        assert status == "completed"

    def test_backup_with_exclude_patterns(
        self,
        test_client: TestClient,
        admin_headers,
        db_borg_repo,
        tmp_path
    ):
        """Test backup with exclude patterns"""
        repo, repo_path, _ = db_borg_repo

        # Create files with different extensions
        source_dir = tmp_path / "exclude-test"
        source_dir.mkdir()

        (source_dir / "keep1.txt").write_text("Keep this file")
        (source_dir / "keep2.txt").write_text("Keep this too")
        (source_dir / "exclude.log").write_text("Exclude this log file")
        (source_dir / "exclude.tmp").write_text("Exclude this temp file")

        repo.source_directories = json.dumps([str(source_dir)])
        repo.exclude_patterns = json.dumps(["*.log", "*.tmp"])

        response = test_client.post(
            "/api/backup/start",
            json={"repository": repo.path},
            headers=admin_headers
        )

        assert response.status_code == 200
        job_id = response.json()["job_id"]

        # Wait for completion
        max_wait = 30
        start_time = time.time()
        status = "pending"

        while status in ["pending", "running"] and (time.time() - start_time) < max_wait:
            time.sleep(1)
            status_response = test_client.get(
                f"/api/backup/jobs/{job_id}",
                headers=admin_headers
            )
            if status_response.status_code == 200:
                status = status_response.json().get("status", "unknown")

        assert status == "completed"


@pytest.mark.integration
@pytest.mark.requires_borg
class TestBackupWithEncryption:
    """Test backups with encrypted repositories"""

    def test_backup_to_encrypted_repository(
        self,
        test_client: TestClient,
        admin_headers,
        db_encrypted_borg_repo,
        tmp_path
    ):
        """Test backup to encrypted repository with passphrase"""
        repo, repo_path, test_data_path, passphrase = db_encrypted_borg_repo

        # Create new source files for backup
        source_dir = tmp_path / "encrypted-backup-source"
        source_dir.mkdir()
        (source_dir / "secret1.txt").write_text("Secret data 1")
        (source_dir / "secret2.txt").write_text("Secret data 2")

        repo.source_directories = json.dumps([str(source_dir)])

        response = test_client.post(
            "/api/backup/start",
            json={"repository": repo.path},
            headers=admin_headers
        )

        assert response.status_code == 200
        job_id = response.json()["job_id"]

        # Wait for completion
        max_wait = 30
        start_time = time.time()
        status = "pending"

        while status in ["pending", "running"] and (time.time() - start_time) < max_wait:
            time.sleep(1)
            status_response = test_client.get(
                f"/api/backup/jobs/{job_id}",
                headers=admin_headers
            )
            if status_response.status_code == 200:
                status = status_response.json().get("status", "unknown")

        assert status == "completed"


@pytest.mark.integration
@pytest.mark.requires_borg
class TestBackupJobManagement:
    """Test backup job lifecycle"""

    def test_list_backup_jobs_shows_completed(
        self,
        test_client: TestClient,
        admin_headers,
        db_borg_repo,
        tmp_path
    ):
        """Test that completed backups appear in job list"""
        repo, repo_path, _ = db_borg_repo

        # Create source
        source_dir = tmp_path / "job-list-source"
        source_dir.mkdir()
        (source_dir / "file.txt").write_text("Test content")

        repo.source_directories = json.dumps([str(source_dir)])

        # Start backup
        response = test_client.post(
            "/api/backup/start",
            json={"repository": repo.path},
            headers=admin_headers
        )

        assert response.status_code == 200
        job_id = response.json()["job_id"]

        # Wait for completion
        max_wait = 30
        start_time = time.time()

        while (time.time() - start_time) < max_wait:
            time.sleep(1)
            status_response = test_client.get(
                f"/api/backup/jobs/{job_id}",
                headers=admin_headers
            )
            if status_response.status_code == 200:
                status = status_response.json().get("status", "unknown")
                if status not in ["pending", "running"]:
                    break

        # List all backup jobs
        list_response = test_client.get(
            "/api/backup/jobs",
            headers=admin_headers
        )

        assert list_response.status_code == 200
        jobs_data = list_response.json()

        # Should have at least our job
        jobs = jobs_data.get("jobs", jobs_data)
        if isinstance(jobs, list):
            assert len(jobs) >= 1
            # Find our job
            our_job = next((j for j in jobs if j["id"] == job_id), None)
            assert our_job is not None
            assert our_job["status"] in ["completed", "failed"]

    def test_get_backup_status(
        self,
        test_client: TestClient,
        admin_headers,
        db_borg_repo,
        tmp_path
    ):
        """Test getting status of a running/completed backup"""
        repo, repo_path, _ = db_borg_repo

        source_dir = tmp_path / "status-test-source"
        source_dir.mkdir()
        (source_dir / "test.txt").write_text("Status test")

        repo.source_directories = json.dumps([str(source_dir)])

        response = test_client.post(
            "/api/backup/start",
            json={"repository": repo.path},
            headers=admin_headers
        )

        job_id = response.json()["job_id"]

        # Check status immediately
        status_response = test_client.get(
            f"/api/backup/jobs/{job_id}",
            headers=admin_headers
        )

        assert status_response.status_code == 200
        status_data = status_response.json()
        assert "status" in status_data
        assert status_data["status"] in ["pending", "running", "completed", "failed"]


@pytest.mark.integration
@pytest.mark.requires_borg
class TestIncrementalBackup:
    """Test incremental backup functionality"""

    def test_incremental_backup_creates_new_archive(
        self,
        test_client: TestClient,
        admin_headers,
        db_borg_repo_with_archives,
        tmp_path
    ):
        """Test that incremental backup creates a new archive"""
        repo, repo_path, test_data_path, existing_archives = db_borg_repo_with_archives

        # Count existing archives
        initial_count = len(existing_archives)

        # Create new source for incremental backup
        source_dir = tmp_path / "incremental-source"
        source_dir.mkdir()
        (source_dir / "new-file.txt").write_text("New content for incremental backup")

        repo.source_directories = json.dumps([str(source_dir)])

        # Perform incremental backup
        response = test_client.post(
            "/api/backup/start",
            json={"repository": repo.path},
            headers=admin_headers
        )

        assert response.status_code == 200
        job_id = response.json()["job_id"]

        # Wait for completion
        max_wait = 30
        start_time = time.time()
        status = "pending"

        while status in ["pending", "running"] and (time.time() - start_time) < max_wait:
            time.sleep(1)
            status_response = test_client.get(
                f"/api/backup/jobs/{job_id}",
                headers=admin_headers
            )
            if status_response.status_code == 200:
                status = status_response.json().get("status", "unknown")

        assert status == "completed"

        # Verify new archive was created
        from app.core.borg import BorgInterface
        import asyncio
        borg = BorgInterface()

        async def check_archives():
            result = await borg.list_archives(repo.path)
            return result

        list_result = asyncio.run(check_archives())
        assert list_result["success"]

        archives_data = json.loads(list_result["stdout"])
        new_archives = archives_data.get("archives", [])

        # Should have one more archive than before
        assert len(new_archives) >= initial_count + 1
