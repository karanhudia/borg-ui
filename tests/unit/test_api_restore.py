"""
Comprehensive unit tests for restore API endpoints
"""
import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient
from app.database.models import Repository, RestoreJob
from tests.unit.helpers import assert_auth_required


@pytest.mark.unit
class TestRestoreRepositories:
    """Test restore repositories listing"""

    def test_list_restore_repositories_success(self, test_client: TestClient, admin_headers, test_db):
        """Test listing repositories for restore returns 200"""
        repo = Repository(name="Test Repo", path="/test/repo", encryption="none", repository_type="local")
        test_db.add(repo)
        test_db.commit()

        response = test_client.get("/api/restore/repositories", headers=admin_headers)

        assert response.status_code == 200
        data = response.json()
        assert "repositories" in data
        assert any(item["path"] == "/test/repo" for item in data["repositories"])

    def test_list_restore_repositories_empty(self, test_client: TestClient, admin_headers):
        """Test listing repositories returns 200 when empty"""
        response = test_client.get("/api/restore/repositories", headers=admin_headers)

        assert response.status_code == 200
        data = response.json()
        assert data == {"repositories": []}

    def test_list_restore_repositories_unauthorized(self, test_client: TestClient):
        """Test listing repositories without auth returns 403"""
        response = test_client.get("/api/restore/repositories")

        assert_auth_required(response)


@pytest.mark.unit
class TestRestoreArchives:
    """Test restore archives listing"""

    def test_list_archives_success(self, test_client: TestClient, admin_headers, test_db):
        """Test listing archives for repository returns 200"""
        repo = Repository(name="Test Repo", path="/test/repo", encryption="none", repository_type="local")
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        process = AsyncMock()
        process.returncode = 0
        process.communicate = AsyncMock(return_value=(b'{"archives":[{"name":"archive1"}]}', b""))
        with patch("app.api.repositories.asyncio.create_subprocess_exec", new=AsyncMock(return_value=process)), \
             patch("app.api.repositories.asyncio.wait_for", new=AsyncMock(return_value=(b'{"archives":[{"name":"archive1"}]}', b""))):

            response = test_client.get(f"/api/restore/archives/{repo.id}", headers=admin_headers)

            assert response.status_code == 200

    def test_list_archives_nonexistent_repo(self, test_client: TestClient, admin_headers):
        """Test listing archives for non-existent repository returns 404"""
        response = test_client.get("/api/restore/archives/99999", headers=admin_headers)

        assert response.status_code == 404

    def test_list_archives_unauthorized(self, test_client: TestClient):
        """Test listing archives without auth returns 403"""
        response = test_client.get("/api/restore/archives/1")

        assert_auth_required(response)


@pytest.mark.unit
class TestRestoreContents:
    """Test restore archive contents"""

    def test_list_contents_success(self, test_client: TestClient, admin_headers, test_db):
        """Test listing archive contents returns 200"""
        repo = Repository(name="Test Repo", path="/test/repo", encryption="none", repository_type="local")
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        with patch("app.api.restore.BorgRouter.list_archive_contents", new_callable=AsyncMock) as mock_list:
            mock_list.return_value = {
                "success": True,
                "stdout": '{"path": "/file.txt", "type": "f"}\n'
            }

            response = test_client.get(
                f"/api/restore/contents/{repo.id}/test-archive",
                headers=admin_headers
            )

            assert response.status_code == 200

    def test_list_contents_with_path_filter(self, test_client: TestClient, admin_headers, test_db):
        """Test listing archive contents with path filter returns 200"""
        repo = Repository(name="Test Repo", path="/test/repo", encryption="none", repository_type="local")
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        with patch("app.api.restore.BorgRouter.list_archive_contents", new_callable=AsyncMock) as mock_list:
            mock_list.return_value = {
                "success": True,
                "stdout": '{"path": "/subdir/file.txt"}\n'
            }

            response = test_client.get(
                f"/api/restore/contents/{repo.id}/test-archive?path=/subdir",
                headers=admin_headers
            )

            assert response.status_code == 200

    def test_list_contents_uses_repo_ssh_environment(self, test_client: TestClient, admin_headers, test_db):
        repo = Repository(
            name="SSH Repo",
            path="ssh://borgsmoke@127.0.0.1:2222/home/borgsmoke/remote-repo",
            encryption="none",
            repository_type="ssh",
            connection_id=1,
        )
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        fake_key_path = "/tmp/test-ssh.key"
        with patch("app.api.restore.archive_cache.get", new_callable=AsyncMock, return_value=None), \
             patch("app.api.restore.resolve_repo_ssh_key_file", return_value=fake_key_path), \
             patch("app.api.restore.os.path.exists", side_effect=lambda path: path == fake_key_path), \
             patch("app.api.restore.os.unlink") as mock_unlink, \
             patch("app.api.restore.BorgRouter.list_archive_contents", new_callable=AsyncMock) as mock_list:
            mock_list.return_value = {
                "success": True,
                "stdout": '{"path": "/ssh-remote.txt", "type": "f"}\n'
            }

            response = test_client.get(
                f"/api/restore/contents/{repo.id}/test-archive",
                headers=admin_headers
            )

        assert response.status_code == 200
        _, kwargs = mock_list.await_args
        assert kwargs["env"]["BORG_RSH"].startswith("ssh -i /tmp/test-ssh.key")
        mock_unlink.assert_called_once_with(fake_key_path)

    def test_list_contents_nonexistent_repo(self, test_client: TestClient, admin_headers):
        """Test listing contents for non-existent repository returns 404"""
        response = test_client.get(
            "/api/restore/contents/99999/test-archive",
            headers=admin_headers
        )

        assert response.status_code == 404

    def test_list_contents_unauthorized(self, test_client: TestClient):
        """Test listing contents without auth returns 403"""
        response = test_client.get("/api/restore/contents/1/test-archive")

        assert_auth_required(response)

    def test_list_contents_empty_archive_name(self, test_client: TestClient, admin_headers, test_db):
        """Whitespace archive names are passed through and still return a payload."""
        repo = Repository(name="Test Repo", path="/test/repo", encryption="none", repository_type="local")
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        with patch('app.api.restore.archive_cache.get', new_callable=AsyncMock, return_value=[]):
            response = test_client.get(
                f"/api/restore/contents/{repo.id}/ ",
                headers=admin_headers
            )

        assert response.status_code == 200
        assert response.json()["items"] == []

    def test_list_contents_uses_v2_router_for_borg2_repositories(self, test_client: TestClient, admin_headers, test_db):
        repo = Repository(
            name="V2 Repo",
            path="/test/v2-repo",
            encryption="none",
            repository_type="local",
            borg_version=2,
        )
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        with patch("app.api.restore.archive_cache.get", new_callable=AsyncMock, return_value=None), \
             patch("app.api.restore.BorgRouter.list_archive_contents", new_callable=AsyncMock) as mock_list:
            mock_list.return_value = {
                "success": True,
                "stdout": '{"path": "photo.jpg", "type": "f"}\n'
            }

            response = test_client.get(
                f"/api/restore/contents/{repo.id}/test-archive",
                headers=admin_headers
            )

        assert response.status_code == 200
        mock_list.assert_awaited_once()


@pytest.mark.unit
class TestRestorePreview:
    """Test restore preview functionality"""

    def test_preview_restore_success(self, test_client: TestClient, admin_headers, test_db):
        """Test previewing restore returns 200"""
        repo = Repository(name="Test Repo", path="/test/repo", encryption="none", repository_type="local")
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        with patch("app.api.restore.BorgRouter.preview_restore", new_callable=AsyncMock) as mock_preview:
            mock_preview.return_value = {"stdout": "preview output"}
            response = test_client.post(
                "/api/restore/preview",
                json={
                    "repository": repo.path,
                    "repository_id": repo.id,
                    "archive": "test-archive",
                    "paths": ["/file1.txt", "/file2.txt"],
                    "destination": "/restore/target"
                },
                headers=admin_headers
            )

        assert response.status_code == 200
        assert response.json()["preview"] == "preview output"
        mock_preview.assert_awaited_once_with(
            archive="test-archive",
            paths=["/file1.txt", "/file2.txt"],
            destination="/restore/target",
        )

    def test_preview_restore_missing_fields(self, test_client: TestClient, admin_headers):
        """Test previewing restore with missing fields returns 422"""
        response = test_client.post(
            "/api/restore/preview",
            json={"repository_id": 1},
            headers=admin_headers
        )

        assert response.status_code == 422

    def test_preview_restore_nonexistent_repo(self, test_client: TestClient, admin_headers):
        """Test previewing restore for non-existent repository returns 404"""
        response = test_client.post(
            "/api/restore/preview",
            json={
                "repository": "/missing/repo",
                "repository_id": 99999,
                "archive": "test-archive",
                "paths": ["/file.txt"],
                "destination": "/restore"
            },
            headers=admin_headers
        )

        assert response.status_code == 404

    def test_preview_restore_unauthorized(self, test_client: TestClient):
        """Test previewing restore without auth returns 403"""
        response = test_client.post(
            "/api/restore/preview",
            json={
                "repository_id": 1,
                "archive_name": "test",
                "files": ["/file.txt"],
                "target_directory": "/restore"
            }
        )

        assert response.status_code == 401

    def test_preview_restore_empty_files_list(self, test_client: TestClient, admin_headers, test_db):
        """Test previewing restore with empty files list"""
        repo = Repository(name="Test Repo", path="/test/repo", encryption="none", repository_type="local")
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        with patch("app.api.restore.BorgRouter.preview_restore", new_callable=AsyncMock) as mock_preview:
            mock_preview.return_value = {"stdout": "preview output"}

            response = test_client.post(
                "/api/restore/preview",
                json={
                    "repository_id": repo.id,
                    "repository": repo.path,
                    "archive": "test-archive",
                    "paths": [],
                    "destination": "/restore"
                },
                headers=admin_headers
            )

        assert response.status_code == 200

    def test_preview_restore_uses_v2_router_for_borg2_repositories(self, test_client: TestClient, admin_headers, test_db):
        repo = Repository(
            name="V2 Repo",
            path="/test/v2-repo",
            encryption="none",
            repository_type="local",
            borg_version=2,
        )
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        with patch("app.api.restore.BorgRouter.preview_restore", new_callable=AsyncMock) as mock_preview:
            mock_preview.return_value = {"stdout": "preview output"}
            response = test_client.post(
                "/api/restore/preview",
                json={
                    "repository": repo.path,
                    "repository_id": repo.id,
                    "archive": "test-archive",
                    "paths": ["/file1.txt"],
                    "destination": "/restore/target"
                },
                headers=admin_headers
            )

        assert response.status_code == 200
        assert response.json()["preview"] == "preview output"
        mock_preview.assert_awaited_once_with(
            archive="test-archive",
            paths=["/file1.txt"],
            destination="/restore/target",
        )

    def test_preview_restore_accepts_repository_id(self, test_client: TestClient, admin_headers, test_db):
        repo = Repository(name="Test Repo", path="/test/repo", encryption="none", repository_type="local")
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        with patch("app.api.restore.BorgRouter.preview_restore", new_callable=AsyncMock) as mock_preview:
            mock_preview.return_value = {"stdout": "preview output"}
            response = test_client.post(
                "/api/restore/preview",
                json={
                    "repository": str(repo.id),
                    "repository_id": repo.id,
                    "archive": "test-archive",
                    "paths": ["/file1.txt"],
                    "destination": "/restore/target"
                },
                headers=admin_headers
            )

        assert response.status_code == 200
        assert response.json()["preview"] == "preview output"
        mock_preview.assert_awaited_once_with(
            archive="test-archive",
            paths=["/file1.txt"],
            destination="/restore/target",
        )


@pytest.mark.unit
class TestRestoreStart:
    """Test starting restore operations"""

    def test_start_restore_invalid_repository(self, test_client: TestClient, admin_headers):
        """Test starting restore with invalid repository"""
        response = test_client.post(
            "/api/restore/start",
            json={
                "repository_id": 99999,
                "repository": "/missing/repo",
                "archive": "test-archive",
                "paths": [],
                "destination": "/tmp/restore"
            },
            headers=admin_headers
        )

        assert response.status_code == 404

    def test_start_restore_missing_fields(self, test_client: TestClient, admin_headers):
        """Test starting restore with missing required fields"""
        response = test_client.post(
            "/api/restore/start",
            json={},
            headers=admin_headers
        )

        assert response.status_code == 422  # Validation error

    def test_start_restore_nonexistent_repo(self, test_client: TestClient, admin_headers):
        """Test starting restore for non-existent repository returns 404"""
        response = test_client.post(
            "/api/restore/start",
            json={
                "repository_id": 99999,
                "repository": "/missing/repo",
                "archive": "test-archive",
                "paths": ["/file.txt"],
                "destination": "/restore"
            },
            headers=admin_headers
        )

        assert response.status_code == 404

    def test_start_restore_invalid_target(self, test_client: TestClient, admin_headers, test_db):
        """Test starting restore with invalid target directory"""
        repo = Repository(name="Test Repo", path="/test/repo", encryption="none", repository_type="local")
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        response = test_client.post(
            "/api/restore/start",
            json={
                "repository_id": repo.id,
                "repository": repo.path,
                "archive": "test-archive",
                "paths": ["/file.txt"],
                "destination": ""
            },
            headers=admin_headers
        )

        assert response.status_code == 200

    def test_start_restore_unauthorized(self, test_client: TestClient):
        """Test starting restore without auth returns 403"""
        response = test_client.post(
            "/api/restore/start",
            json={
                "repository_id": 1,
                "archive_name": "test",
                "files": ["/file.txt"],
                "target_directory": "/restore"
            }
        )

        assert response.status_code == 401

    def test_start_restore_empty_files_list(self, test_client: TestClient, admin_headers, test_db):
        """Test starting restore with empty files list"""
        repo = Repository(name="Test Repo", path="/test/repo", encryption="none", repository_type="local")
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        response = test_client.post(
            "/api/restore/start",
            json={
                "repository_id": repo.id,
                "repository": repo.path,
                "archive": "test-archive",
                "paths": [],
                "destination": "/restore"
            },
            headers=admin_headers
        )

        assert response.status_code == 200

    def test_start_restore_accepts_repository_id_in_repository_field(self, test_client: TestClient, admin_headers, test_db):
        repo = Repository(name="Test Repo", path="/test/repo", encryption="none", repository_type="local")
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        with patch("app.api.restore.asyncio.create_task", return_value=object()) as mock_create_task:
            response = test_client.post(
                "/api/restore/start",
                json={
                    "repository_id": repo.id,
                    "repository": str(repo.id),
                    "archive": "test-archive",
                    "paths": ["/file.txt"],
                    "destination": "/restore"
                },
                headers=admin_headers
            )

        assert response.status_code == 200
        job = test_db.query(RestoreJob).order_by(RestoreJob.id.desc()).first()
        assert job is not None
        assert job.repository == repo.path
        scheduled = mock_create_task.call_args.args[0]
        scheduled.close()


@pytest.mark.unit
class TestRestoreJobs:
    """Test restore job management"""

    def test_list_restore_jobs_empty(self, test_client: TestClient, admin_headers):
        """Test listing restore jobs when none exist"""
        response = test_client.get("/api/restore/jobs", headers=admin_headers)

        assert response.status_code == 200
        data = response.json()
        assert data == {"jobs": []}

    def test_list_restore_jobs_success(self, test_client: TestClient, admin_headers):
        """Test listing restore jobs returns 200"""
        response = test_client.get("/api/restore/jobs", headers=admin_headers)

        assert response.status_code == 200
        data = response.json()
        assert "jobs" in data
        assert isinstance(data["jobs"], list)

    def test_list_restore_jobs_unauthorized(self, test_client: TestClient):
        """Test listing restore jobs without authentication"""
        response = test_client.get("/api/restore/jobs")

        assert_auth_required(response)

    def test_get_restore_job_status_nonexistent(self, test_client: TestClient, admin_headers):
        """Test getting status of non-existent restore job"""
        response = test_client.get("/api/restore/jobs/99999/status", headers=admin_headers)

        assert response.status_code == 404

    def test_get_restore_job_status_nonexistent_new_endpoint(self, test_client: TestClient, admin_headers):
        """Test getting status for non-existent job returns 404"""
        response = test_client.get("/api/restore/status/99999", headers=admin_headers)

        assert response.status_code == 404

    def test_get_restore_job_status_unauthorized(self, test_client: TestClient):
        """Test getting job status without auth returns 403"""
        response = test_client.get("/api/restore/status/1")

        assert response.status_code == 401

    def test_cancel_restore_nonexistent(self, test_client: TestClient, admin_headers):
        """Test canceling non-existent restore job"""
        response = test_client.post(
            "/api/restore/jobs/99999/cancel",
            headers=admin_headers
        )

        assert response.status_code == 405

    def test_cancel_restore_running_job_marks_cancelled(
        self,
        test_client: TestClient,
        admin_headers,
        test_db,
    ):
        repo = Repository(name="Restore Repo", path="/test/repo", encryption="none", repository_type="local")
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        job = RestoreJob(
            repository=repo.path,
            archive="test-archive",
            destination="/restore/target",
            status="running",
        )
        test_db.add(job)
        test_db.commit()
        test_db.refresh(job)

        with patch("app.api.restore.restore_service.cancel_restore", new=AsyncMock(return_value=True)) as mock_cancel:
            response = test_client.post(
                f"/api/restore/cancel/{job.id}",
                headers=admin_headers,
            )

        assert response.status_code == 200
        assert response.json()["message"] == "backend.success.restore.restoreCancelled"
        mock_cancel.assert_awaited_once_with(job.id)

        test_db.expire_all()
        refreshed = test_db.query(RestoreJob).filter(RestoreJob.id == job.id).first()
        assert refreshed.status == "cancelled"
        assert refreshed.completed_at is not None

    def test_cancel_restore_non_running_job_returns_400(
        self,
        test_client: TestClient,
        admin_headers,
        test_db,
    ):
        repo = Repository(name="Restore Repo", path="/test/repo-nonrunning", encryption="none", repository_type="local")
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        job = RestoreJob(
            repository=repo.path,
            archive="test-archive",
            destination="/restore/target",
            status="completed",
        )
        test_db.add(job)
        test_db.commit()
        test_db.refresh(job)

        response = test_client.post(
            f"/api/restore/cancel/{job.id}",
            headers=admin_headers,
        )

        assert response.status_code == 400
        assert response.json()["detail"]["key"] == "backend.errors.restore.canOnlyCancelRunningJobs"

    def test_restore_logs_nonexistent_job(self, test_client: TestClient, admin_headers):
        """Test getting logs for non-existent restore job"""
        response = test_client.get(
            "/api/restore/jobs/99999/logs",
            headers=admin_headers
        )

        assert response.status_code == 404

@pytest.mark.unit
class TestRestoreSpeedAndETA:
    """Test restore speed and ETA tracking functionality"""

    def test_restore_job_includes_speed_and_eta_fields(self, test_client: TestClient, admin_headers, test_db):
        """Test that restore job API responses include speed and ETA fields"""
        from app.database.models import RestoreJob
        from datetime import datetime, timezone
        
        # Create a running restore job with speed and ETA
        job = RestoreJob(
            repository="/test/repo",
            archive="test-archive",
            destination="/test/dest",
            status="running",
            started_at=datetime.now(timezone.utc),
            nfiles=100,
            current_file="/test/file.txt",
            progress_percent=45.5,
            original_size=10485760,  # 10 MB
            restored_size=4767744,   # ~4.5 MB
            restore_speed=12.34,     # MB/s
            estimated_time_remaining=135  # seconds
        )
        test_db.add(job)
        test_db.commit()
        test_db.refresh(job)

        # Get job status
        response = test_client.get(f"/api/restore/status/{job.id}", headers=admin_headers)
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify speed and ETA are included
        assert "progress_details" in data
        progress = data["progress_details"]
        assert "restore_speed" in progress
        assert "estimated_time_remaining" in progress
        assert progress["restore_speed"] == 12.34
        assert progress["estimated_time_remaining"] == 135

    def test_restore_jobs_list_includes_speed_and_eta(self, test_client: TestClient, admin_headers, test_db):
        """Test that restore jobs list includes speed and ETA fields"""
        from app.database.models import RestoreJob
        from datetime import datetime, timezone
        
        # Create restore jobs with different states
        jobs_data = [
            {
                "repository": "/test/repo1",
                "archive": "archive1",
                "destination": "/test/dest1",
                "status": "running",
                "started_at": datetime.now(timezone.utc),
                "restore_speed": 15.67,
                "estimated_time_remaining": 240
            },
            {
                "repository": "/test/repo2",
                "archive": "archive2",
                "destination": "/test/dest2",
                "status": "completed",
                "started_at": datetime.now(timezone.utc),
                "completed_at": datetime.now(timezone.utc),
                "restore_speed": 0.0,
                "estimated_time_remaining": 0
            }
        ]
        
        for job_data in jobs_data:
            job = RestoreJob(**job_data)
            test_db.add(job)
        test_db.commit()

        # Get jobs list
        response = test_client.get("/api/restore/jobs", headers=admin_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert "jobs" in data
        
        # Verify all jobs have speed and ETA fields
        for job in data["jobs"]:
            assert "progress_details" in job
            progress = job["progress_details"]
            assert "restore_speed" in progress
            assert "estimated_time_remaining" in progress

    def test_restore_speed_defaults_to_zero(self, test_client: TestClient, admin_headers, test_db):
        """Test that restore speed defaults to 0.0 when not set"""
        from app.database.models import RestoreJob
        
        job = RestoreJob(
            repository="/test/repo",
            archive="test-archive",
            destination="/test/dest",
            status="pending"
        )
        test_db.add(job)
        test_db.commit()
        test_db.refresh(job)

        response = test_client.get(f"/api/restore/status/{job.id}", headers=admin_headers)
        
        assert response.status_code == 200
        data = response.json()
        progress = data["progress_details"]
        assert progress["restore_speed"] == 0.0
        assert progress["estimated_time_remaining"] == 0

    def test_restore_eta_zero_when_speed_zero(self, test_client: TestClient, admin_headers, test_db):
        """Test that ETA is 0 when restore speed is 0"""
        from app.database.models import RestoreJob
        from datetime import datetime, timezone
        
        job = RestoreJob(
            repository="/test/repo",
            archive="test-archive",
            destination="/test/dest",
            status="running",
            started_at=datetime.now(timezone.utc),
            original_size=10485760,
            restored_size=1048576,
            restore_speed=0.0,  # No speed yet
            estimated_time_remaining=0
        )
        test_db.add(job)
        test_db.commit()
        test_db.refresh(job)

        response = test_client.get(f"/api/restore/status/{job.id}", headers=admin_headers)
        
        assert response.status_code == 200
        data = response.json()
        progress = data["progress_details"]
        assert progress["estimated_time_remaining"] == 0

    def test_restore_completed_job_speed_preserved(self, test_client: TestClient, admin_headers, test_db):
        """Test that completed restore jobs preserve final speed"""
        from app.database.models import RestoreJob
        from datetime import datetime, timezone
        
        job = RestoreJob(
            repository="/test/repo",
            archive="test-archive",
            destination="/test/dest",
            status="completed",
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
            original_size=10485760,
            restored_size=10485760,
            restore_speed=18.92,  # Final speed preserved
            estimated_time_remaining=0,
            progress_percent=100.0
        )
        test_db.add(job)
        test_db.commit()
        test_db.refresh(job)

        response = test_client.get(f"/api/restore/status/{job.id}", headers=admin_headers)
        
        assert response.status_code == 200
        data = response.json()
        progress = data["progress_details"]
        assert progress["restore_speed"] == 18.92
        assert progress["estimated_time_remaining"] == 0
        assert data["status"] == "completed"

@pytest.mark.unit
class TestRestoreJobLogs:
    """Test restore job logs functionality"""

    def test_restore_jobs_list_includes_logs(self, test_client: TestClient, admin_headers, test_db):
        """Test that /api/restore/jobs endpoint includes logs field"""
        from app.database.models import RestoreJob
        from datetime import datetime, timezone
        
        job = RestoreJob(
            repository="/test/repo",
            archive="test-archive",
            destination="/test/dest",
            status="completed",
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
            logs="Test log line 1\nTest log line 2\nRestore completed"
        )
        test_db.add(job)
        test_db.commit()
        test_db.refresh(job)

        response = test_client.get("/api/restore/jobs", headers=admin_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert "jobs" in data
        assert len(data["jobs"]) > 0
        
        # Find our job
        our_job = next((j for j in data["jobs"] if j["id"] == job.id), None)
        assert our_job is not None
        assert "logs" in our_job
        assert our_job["logs"] == job.logs

    def test_restore_job_status_includes_logs(self, test_client: TestClient, admin_headers, test_db):
        """Test that /api/restore/status/{id} endpoint includes logs field"""
        from app.database.models import RestoreJob
        from datetime import datetime, timezone
        
        job = RestoreJob(
            repository="/test/repo",
            archive="test-archive",
            destination="/test/dest",
            status="completed",
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
            logs="Detailed restore logs here\nProgress: 100%\nSuccess"
        )
        test_db.add(job)
        test_db.commit()
        test_db.refresh(job)

        response = test_client.get(f"/api/restore/status/{job.id}", headers=admin_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert "logs" in data
        assert data["logs"] == job.logs

    def test_restore_jobs_with_null_logs(self, test_client: TestClient, admin_headers, test_db):
        """Test that jobs with null logs return null in API"""
        from app.database.models import RestoreJob
        from datetime import datetime, timezone
        
        job = RestoreJob(
            repository="/test/repo",
            archive="test-archive",
            destination="/test/dest",
            status="running",
            started_at=datetime.now(timezone.utc),
            logs=None  # No logs yet for running job
        )
        test_db.add(job)
        test_db.commit()
        test_db.refresh(job)

        response = test_client.get("/api/restore/jobs", headers=admin_headers)
        
        assert response.status_code == 200
        data = response.json()
        our_job = next((j for j in data["jobs"] if j["id"] == job.id), None)
        assert our_job is not None
        assert our_job["logs"] is None

    def test_restore_jobs_with_empty_logs(self, test_client: TestClient, admin_headers, test_db):
        """Test that jobs with empty string logs return empty string"""
        from app.database.models import RestoreJob
        from datetime import datetime, timezone
        
        job = RestoreJob(
            repository="/test/repo",
            archive="test-archive",
            destination="/test/dest",
            status="completed",
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
            logs=""  # Empty logs
        )
        test_db.add(job)
        test_db.commit()
        test_db.refresh(job)

        response = test_client.get(f"/api/restore/status/{job.id}", headers=admin_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert "logs" in data
        assert data["logs"] == ""

    def test_restore_jobs_with_multiline_logs(self, test_client: TestClient, admin_headers, test_db):
        """Test that multiline logs are preserved correctly"""
        from app.database.models import RestoreJob
        from datetime import datetime, timezone
        
        multiline_logs = """Starting restore operation
Repository: /test/repo
Archive: test-archive
Destination: /test/dest
Progress: 50%
Progress: 75%
Progress: 100%
Restore completed successfully"""
        
        job = RestoreJob(
            repository="/test/repo",
            archive="test-archive",
            destination="/test/dest",
            status="completed",
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
            logs=multiline_logs
        )
        test_db.add(job)
        test_db.commit()
        test_db.refresh(job)

        response = test_client.get(f"/api/restore/status/{job.id}", headers=admin_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["logs"] == multiline_logs
        # Verify line breaks are preserved
        assert "\n" in data["logs"]
        assert data["logs"].count("\n") == multiline_logs.count("\n")
