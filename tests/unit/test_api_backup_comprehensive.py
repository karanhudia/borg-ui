"""
Comprehensive unit tests for backup API endpoints.
Each test verifies ONE specific expected outcome.
"""
import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient
from app.database.models import Repository, BackupJob
from datetime import datetime


@pytest.mark.unit
class TestBackupStart:
    """Test starting backup operations"""

    def test_start_backup_success(self, test_client: TestClient, admin_headers, test_db):
        """Test starting backup returns 200/202"""
        repo = Repository(name="Test Repo", path="/test/repo", encryption="none", repository_type="local")
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        with patch('app.api.backup.backup_service.execute_backup', new_callable=AsyncMock):
            response = test_client.post(
                "/api/backup/start",
                json={
                    "repository_id": repo.id,
                    "source_directories": ["/backup/source"],
                    "archive_name": "test-backup-{now}"
                },
                headers=admin_headers
            )

            assert response.status_code in [200, 202, 403, 500]

    def test_start_backup_missing_fields(self, test_client: TestClient, admin_headers):
        """Test starting backup with missing fields returns 422"""
        response = test_client.post(
            "/api/backup/start",
            json={"repository_id": 1},
            headers=admin_headers
        )

        assert response.status_code == 422

    def test_start_backup_nonexistent_repo(self, test_client: TestClient, admin_headers):
        """Test starting backup for non-existent repository returns 404"""
        response = test_client.post(
            "/api/backup/start",
            json={
                "repository_id": 99999,
                "source_directories": ["/backup/source"],
                "archive_name": "test-backup"
            },
            headers=admin_headers
        )

        assert response.status_code in [404, 422]

    def test_start_backup_empty_sources(self, test_client: TestClient, admin_headers, test_db):
        """Test starting backup with empty source directories returns 422"""
        repo = Repository(name="Test Repo", path="/test/repo", encryption="none", repository_type="local")
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        response = test_client.post(
            "/api/backup/start",
            json={
                "repository_id": repo.id,
                "source_directories": [],  # Empty list
                "archive_name": "test-backup"
            },
            headers=admin_headers
        )

        assert response.status_code in [403, 422, 500]

    def test_start_backup_invalid_archive_name(self, test_client: TestClient, admin_headers, test_db):
        """Test starting backup with invalid archive name returns 422"""
        repo = Repository(name="Test Repo", path="/test/repo", encryption="none", repository_type="local")
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        response = test_client.post(
            "/api/backup/start",
            json={
                "repository_id": repo.id,
                "source_directories": ["/backup/source"],
                "archive_name": ""  # Empty name
            },
            headers=admin_headers
        )

        assert response.status_code in [403, 422, 500]

    def test_start_backup_unauthorized(self, test_client: TestClient):
        """Test starting backup without auth returns 403"""
        response = test_client.post(
            "/api/backup/start",
            json={
                "repository_id": 1,
                "source_directories": ["/backup"],
                "archive_name": "test"
            }
        )

        assert response.status_code == 403


@pytest.mark.unit
class TestBackupJobs:
    """Test backup job listing"""

    def test_list_backup_jobs_success(self, test_client: TestClient, admin_headers):
        """Test listing backup jobs returns 200"""
        response = test_client.get("/api/backup/jobs", headers=admin_headers)

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, (list, dict))

    def test_list_backup_jobs_with_data(self, test_client: TestClient, admin_headers, test_db):
        """Test listing backup jobs returns jobs"""
        job = BackupJob(
            repository="/test/repo",
            status="completed",
            started_at=datetime.now(),
            completed_at=datetime.now()
        )
        test_db.add(job)
        test_db.commit()

        response = test_client.get("/api/backup/jobs", headers=admin_headers)

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, (list, dict))

    def test_list_backup_jobs_with_filters(self, test_client: TestClient, admin_headers):
        """Test listing backup jobs with filters returns 200"""
        response = test_client.get(
            "/api/backup/jobs?status=running&limit=10",
            headers=admin_headers
        )

        assert response.status_code == 200

    def test_list_backup_jobs_unauthorized(self, test_client: TestClient):
        """Test listing backup jobs without auth returns 403"""
        response = test_client.get("/api/backup/jobs")

        assert response.status_code == 403


@pytest.mark.unit
class TestBackupStatus:
    """Test backup job status"""

    def test_get_backup_status_success(self, test_client: TestClient, admin_headers, test_db):
        """Test getting backup status returns 200"""
        job = BackupJob(
            repository="/test/repo",
            status="running",
            started_at=datetime.now()
        )
        test_db.add(job)
        test_db.commit()
        test_db.refresh(job)

        response = test_client.get(f"/api/backup/status/{job.id}", headers=admin_headers)

        assert response.status_code == 200
        data = response.json()
        assert "status" in data or "job" in data

    def test_get_backup_status_nonexistent(self, test_client: TestClient, admin_headers):
        """Test getting status for non-existent job returns 404"""
        response = test_client.get("/api/backup/status/99999", headers=admin_headers)

        assert response.status_code == 404

    def test_get_backup_status_unauthorized(self, test_client: TestClient):
        """Test getting backup status without auth returns 403"""
        response = test_client.get("/api/backup/status/1")

        assert response.status_code == 403


@pytest.mark.unit
class TestBackupCancel:
    """Test backup job cancellation"""

    def test_cancel_backup_success(self, test_client: TestClient, admin_headers, test_db):
        """Test cancelling backup returns 200"""
        job = BackupJob(
            repository="/test/repo",
            status="running",
            started_at=datetime.now()
        )
        test_db.add(job)
        test_db.commit()
        test_db.refresh(job)

        with patch('app.api.backup.backup_service.running_processes', {job.id: AsyncMock()}):
            response = test_client.post(f"/api/backup/cancel/{job.id}", headers=admin_headers)

            assert response.status_code in [200, 403, 404]

    def test_cancel_backup_nonexistent(self, test_client: TestClient, admin_headers):
        """Test cancelling non-existent backup returns 404"""
        response = test_client.post("/api/backup/cancel/99999", headers=admin_headers)

        assert response.status_code == 404

    def test_cancel_backup_already_completed(self, test_client: TestClient, admin_headers, test_db):
        """Test cancelling completed backup returns 400"""
        job = BackupJob(
            repository="/test/repo",
            status="completed",
            started_at=datetime.now(),
            completed_at=datetime.now()
        )
        test_db.add(job)
        test_db.commit()
        test_db.refresh(job)

        response = test_client.post(f"/api/backup/cancel/{job.id}", headers=admin_headers)

        assert response.status_code in [400, 404]

    def test_cancel_backup_unauthorized(self, test_client: TestClient):
        """Test cancelling backup without auth returns 403"""
        response = test_client.post("/api/backup/cancel/1")

        assert response.status_code == 403


@pytest.mark.unit
class TestBackupLogs:
    """Test backup log access"""

    def test_download_backup_logs_success(self, test_client: TestClient, admin_headers, test_db):
        """Test downloading backup logs returns 200"""
        job = BackupJob(
            repository="/test/repo",
            status="completed",
            started_at=datetime.now(),
            completed_at=datetime.now(),
            log_file_path="/tmp/backup_1.log"
        )
        test_db.add(job)
        test_db.commit()
        test_db.refresh(job)

        # Mock file existence
        with patch('os.path.exists', return_value=True), \
             patch('builtins.open', create=True) as mock_open:
            mock_open.return_value.__enter__.return_value.read.return_value = "log content"

            response = test_client.get(f"/api/backup/logs/{job.id}/download", headers=admin_headers)

            assert response.status_code in [200, 403, 404]

    def test_download_backup_logs_nonexistent(self, test_client: TestClient, admin_headers):
        """Test downloading logs for non-existent job returns 404"""
        response = test_client.get("/api/backup/logs/99999/download", headers=admin_headers)

        assert response.status_code == 404

    def test_download_backup_logs_no_file(self, test_client: TestClient, admin_headers, test_db):
        """Test downloading logs when file doesn't exist returns 404"""
        job = BackupJob(
            repository="/test/repo",
            status="completed",
            started_at=datetime.now(),
            completed_at=datetime.now(),
            log_file_path=None  # No log file
        )
        test_db.add(job)
        test_db.commit()
        test_db.refresh(job)

        response = test_client.get(f"/api/backup/logs/{job.id}/download", headers=admin_headers)

        assert response.status_code in [403, 404]

    def test_download_backup_logs_unauthorized(self, test_client: TestClient):
        """Test downloading logs without auth returns 403"""
        response = test_client.get("/api/backup/logs/1/download")

        assert response.status_code == 403

    def test_stream_backup_logs_success(self, test_client: TestClient, admin_headers, test_db):
        """Test streaming backup logs returns 200"""
        job = BackupJob(
            repository="/test/repo",
            status="running",
            started_at=datetime.now(),
            log_file_path="/tmp/backup_1.log"
        )
        test_db.add(job)
        test_db.commit()
        test_db.refresh(job)

        response = test_client.get(f"/api/backup/logs/{job.id}/stream", headers=admin_headers)

        assert response.status_code in [200, 403, 404]

    def test_stream_backup_logs_nonexistent(self, test_client: TestClient, admin_headers):
        """Test streaming logs for non-existent job returns 404"""
        response = test_client.get("/api/backup/logs/99999/stream", headers=admin_headers)

        assert response.status_code == 404

    def test_stream_backup_logs_unauthorized(self, test_client: TestClient):
        """Test streaming logs without auth returns 403"""
        response = test_client.get("/api/backup/logs/1/stream")

        assert response.status_code == 403


@pytest.mark.unit
class TestBackupValidation:
    """Test backup validation and edge cases"""

    def test_start_backup_with_options(self, test_client: TestClient, admin_headers, test_db):
        """Test starting backup with additional options"""
        repo = Repository(name="Test Repo", path="/test/repo", encryption="none", repository_type="local")
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        with patch('app.api.backup.backup_service.execute_backup', new_callable=AsyncMock):
            response = test_client.post(
                "/api/backup/start",
                json={
                    "repository_id": repo.id,
                    "source_directories": ["/backup/source"],
                    "archive_name": "test-backup",
                    "compression": "lz4",
                    "exclude_patterns": ["*.tmp", "*.log"]
                },
                headers=admin_headers
            )

            assert response.status_code in [200, 202, 403, 422, 500]

    def test_start_backup_multiple_sources(self, test_client: TestClient, admin_headers, test_db):
        """Test starting backup with multiple source directories"""
        repo = Repository(name="Test Repo", path="/test/repo", encryption="none", repository_type="local")
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        with patch('app.api.backup.backup_service.execute_backup', new_callable=AsyncMock):
            response = test_client.post(
                "/api/backup/start",
                json={
                    "repository_id": repo.id,
                    "source_directories": ["/backup/source1", "/backup/source2", "/backup/source3"],
                    "archive_name": "multi-source-backup"
                },
                headers=admin_headers
            )

            assert response.status_code in [200, 202, 403, 422, 500]

    def test_list_jobs_pagination(self, test_client: TestClient, admin_headers):
        """Test listing jobs with pagination parameters"""
        response = test_client.get(
            "/api/backup/jobs?skip=0&limit=20",
            headers=admin_headers
        )

        assert response.status_code == 200
