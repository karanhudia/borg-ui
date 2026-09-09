"""
Comprehensive unit tests for restore API endpoints
"""

import pytest
from pathlib import Path
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient
from app.database.models import (
    Operation,
    OperationRestoreDetails,
    Repository,
    RestoreJob,
    SystemSettings,
)
from tests.unit.helpers import assert_auth_required


def _set_log_save_policy(test_db, policy: str) -> None:
    settings = test_db.query(SystemSettings).first()
    if settings is None:
        settings = SystemSettings()
        test_db.add(settings)
    settings.log_save_policy = policy
    test_db.flush()


@pytest.mark.unit
class TestRestorePreview:
    """Test restore preview functionality"""

    def test_preview_restore_success(
        self, test_client: TestClient, admin_headers, test_db
    ):
        """Test previewing restore returns 200"""
        repo = Repository(
            name="Test Repo",
            path="/test/repo",
            encryption="none",
            repository_type="local",
        )
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        with patch(
            "app.api.restore.BorgRouter.preview_restore", new_callable=AsyncMock
        ) as mock_preview:
            mock_preview.return_value = {"stdout": "preview output"}
            response = test_client.post(
                "/api/restore/preview",
                json={
                    "repository": repo.path,
                    "repository_id": repo.id,
                    "archive": "test-archive",
                    "paths": ["/file1.txt", "/file2.txt"],
                    "destination": "/restore/target",
                },
                headers=admin_headers,
            )

        assert response.status_code == 200
        assert response.json()["preview"] == "preview output"
        mock_preview.assert_awaited_once_with(
            archive="test-archive",
            paths=["/file1.txt", "/file2.txt"],
            destination="/restore/target",
        )

    def test_preview_restore_missing_fields(
        self, test_client: TestClient, admin_headers
    ):
        """Test previewing restore with missing fields returns 422"""
        response = test_client.post(
            "/api/restore/preview", json={"repository_id": 1}, headers=admin_headers
        )

        assert response.status_code == 422

    def test_preview_restore_nonexistent_repo(
        self, test_client: TestClient, admin_headers
    ):
        """Test previewing restore for non-existent repository returns 404"""
        response = test_client.post(
            "/api/restore/preview",
            json={
                "repository": "/missing/repo",
                "repository_id": 99999,
                "archive": "test-archive",
                "paths": ["/file.txt"],
                "destination": "/restore",
            },
            headers=admin_headers,
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
                "target_directory": "/restore",
            },
        )

        assert response.status_code == 401

    def test_preview_restore_empty_files_list(
        self, test_client: TestClient, admin_headers, test_db
    ):
        """Test previewing restore with empty files list"""
        repo = Repository(
            name="Test Repo",
            path="/test/repo",
            encryption="none",
            repository_type="local",
        )
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        with patch(
            "app.api.restore.BorgRouter.preview_restore", new_callable=AsyncMock
        ) as mock_preview:
            mock_preview.return_value = {"stdout": "preview output"}

            response = test_client.post(
                "/api/restore/preview",
                json={
                    "repository_id": repo.id,
                    "repository": repo.path,
                    "archive": "test-archive",
                    "paths": [],
                    "destination": "/restore",
                },
                headers=admin_headers,
            )

        assert response.status_code == 200

    def test_preview_restore_uses_v2_router_for_borg2_repositories(
        self, test_client: TestClient, admin_headers, test_db
    ):
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

        with patch(
            "app.api.restore.BorgRouter.preview_restore", new_callable=AsyncMock
        ) as mock_preview:
            mock_preview.return_value = {"stdout": "preview output"}
            response = test_client.post(
                "/api/restore/preview",
                json={
                    "repository": repo.path,
                    "repository_id": repo.id,
                    "archive": "test-archive",
                    "paths": ["/file1.txt"],
                    "destination": "/restore/target",
                },
                headers=admin_headers,
            )

        assert response.status_code == 200
        assert response.json()["preview"] == "preview output"
        mock_preview.assert_awaited_once_with(
            archive="test-archive",
            paths=["/file1.txt"],
            destination="/restore/target",
        )

    def test_preview_restore_accepts_repository_id(
        self, test_client: TestClient, admin_headers, test_db
    ):
        repo = Repository(
            name="Test Repo",
            path="/test/repo",
            encryption="none",
            repository_type="local",
        )
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        with patch(
            "app.api.restore.BorgRouter.preview_restore", new_callable=AsyncMock
        ) as mock_preview:
            mock_preview.return_value = {"stdout": "preview output"}
            response = test_client.post(
                "/api/restore/preview",
                json={
                    "repository": str(repo.id),
                    "repository_id": repo.id,
                    "archive": "test-archive",
                    "paths": ["/file1.txt"],
                    "destination": "/restore/target",
                },
                headers=admin_headers,
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

    def test_start_restore_invalid_repository(
        self, test_client: TestClient, admin_headers
    ):
        """Test starting restore with invalid repository"""
        response = test_client.post(
            "/api/restore/start",
            json={
                "repository_id": 99999,
                "repository": "/missing/repo",
                "archive": "test-archive",
                "paths": [],
                "destination": "/tmp/restore",
            },
            headers=admin_headers,
        )

        assert response.status_code == 404

    def test_start_restore_missing_fields(self, test_client: TestClient, admin_headers):
        """Test starting restore with missing required fields"""
        response = test_client.post(
            "/api/restore/start", json={}, headers=admin_headers
        )

        assert response.status_code == 422  # Validation error

    def test_start_restore_nonexistent_repo(
        self, test_client: TestClient, admin_headers
    ):
        """Test starting restore for non-existent repository returns 404"""
        response = test_client.post(
            "/api/restore/start",
            json={
                "repository_id": 99999,
                "repository": "/missing/repo",
                "archive": "test-archive",
                "paths": ["/file.txt"],
                "destination": "/restore",
            },
            headers=admin_headers,
        )

        assert response.status_code == 404

    def test_start_restore_invalid_target(
        self, test_client: TestClient, admin_headers, test_db
    ):
        """Test starting restore with invalid target directory"""
        repo = Repository(
            name="Test Repo",
            path="/test/repo",
            encryption="none",
            repository_type="local",
        )
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
                "destination": "",
            },
            headers=admin_headers,
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
                "target_directory": "/restore",
            },
        )

        assert response.status_code == 401

    def test_start_restore_empty_files_list(
        self, test_client: TestClient, admin_headers, test_db
    ):
        """Test starting restore with empty files list"""
        repo = Repository(
            name="Test Repo",
            path="/test/repo",
            encryption="none",
            repository_type="local",
        )
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
                "destination": "/restore",
            },
            headers=admin_headers,
        )

        assert response.status_code == 200

    def test_start_restore_enqueues_an_operation_with_details(
        self, test_client: TestClient, admin_headers, test_db
    ):
        repo = Repository(
            name="Restore Repo",
            path="/test/restore-repo",
            encryption="none",
            repository_type="local",
        )
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        # The live runner may dispatch the row before this test reads it back;
        # a mocked service keeps that harmless. The assertions below do not
        # depend on whether it ran.
        with patch(
            "app.services.restore_service.restore_service.execute_restore",
            new=AsyncMock(return_value=None),
        ):
            response = test_client.post(
                "/api/restore/start",
                json={
                    "repository": repo.path,
                    "repository_id": repo.id,
                    "archive": "test-archive",
                    "paths": ["docs/"],
                    "destination": "/restore/target",
                    "restore_layout": "contents_only",
                    "path_metadata": [{"path": "docs/", "type": "directory"}],
                },
                headers=admin_headers,
            )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "pending"
        assert body["message"] == "backend.success.restore.restoreJobStarted"

        operation = test_db.get(Operation, body["job_id"])
        assert operation.kind == "restore"
        assert operation.category == "restore"
        assert operation.trigger == "manual"
        assert operation.repository_id == repo.id
        assert operation.execution_mode == "server"
        assert operation.params == {
            "archive_name": "test-archive",
            "paths": ["docs/"],
            "restore_layout": "contents_only",
            "path_metadata": [{"path": "docs/", "type": "directory"}],
        }
        details = test_db.get(OperationRestoreDetails, operation.id)
        assert details.archive == "test-archive"
        assert details.destination == "/restore/target"
        assert details.destination_type == "local"
        assert details.repository_type == "local"
        assert test_db.query(RestoreJob).count() == 0

    def test_start_restore_records_the_ssh_destination_on_the_details_row(
        self, test_client: TestClient, admin_headers, test_db
    ):
        from app.database.models import SSHConnection

        repo = Repository(
            name="Restore Repo",
            path="/test/restore-repo",
            encryption="none",
            repository_type="local",
        )
        connection = SSHConnection(host="backup.example", username="borg", port=22)
        test_db.add_all([repo, connection])
        test_db.commit()
        test_db.refresh(repo)
        test_db.refresh(connection)

        with patch(
            "app.services.restore_service.restore_service.execute_restore",
            new=AsyncMock(return_value=None),
        ):
            response = test_client.post(
                "/api/restore/start",
                json={
                    "repository": repo.path,
                    "repository_id": repo.id,
                    "archive": "test-archive",
                    "paths": [],
                    "destination": "/srv/restore",
                    "destination_type": "ssh",
                    "destination_connection_id": connection.id,
                },
                headers=admin_headers,
            )

        assert response.status_code == 200
        details = test_db.get(OperationRestoreDetails, response.json()["job_id"])
        assert details.destination_type == "ssh"
        assert details.destination_connection_id == connection.id
        assert details.destination_hostname == "backup.example"

    def test_status_reads_an_operation_with_the_legacy_shape(
        self, test_client: TestClient, admin_headers, test_db
    ):
        from app.services.operations.details import restore_details

        repo = Repository(
            name="Restore Repo",
            path="/test/restore-repo",
            encryption="none",
            repository_type="local",
        )
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)
        op = Operation(
            repository_id=repo.id,
            kind="restore",
            category="restore",
            status="running",
            trigger="manual",
            priority=0,
            run_id="run-status",
            progress_percent=40.0,
            params={"archive_name": "test-archive"},
        )
        test_db.add(op)
        test_db.flush()
        details = restore_details(test_db, op)
        details.archive = "test-archive"
        details.destination = "/restore/target"
        details.original_size = 10 * 1024 * 1024
        details.restored_size = 4 * 1024 * 1024
        details.restore_speed = 2.0
        details.nfiles = 7
        details.current_file = "docs/report.txt"
        test_db.commit()

        response = test_client.get(
            f"/api/restore/status/{op.id}", headers=admin_headers
        )

        assert response.status_code == 200
        body = response.json()
        assert body["id"] == op.id
        assert body["repository"] == repo.path
        assert body["archive"] == "test-archive"
        assert body["destination"] == "/restore/target"
        assert body["status"] == "running"
        assert body["progress"] == 40
        assert body["progress_details"] == {
            "nfiles": 7,
            "current_file": "docs/report.txt",
            "progress_percent": 40.0,
            "restore_speed": 2.0,
            "estimated_time_remaining": 3,
        }

    def test_list_unions_operations_and_legacy_rows(
        self, test_client: TestClient, admin_headers, test_db
    ):
        from app.services.operations.details import restore_details

        repo = Repository(
            name="Restore Repo",
            path="/test/restore-repo",
            encryption="none",
            repository_type="local",
        )
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)
        legacy = RestoreJob(
            repository=repo.path, archive="old", destination="/x", status="completed"
        )
        op = Operation(
            repository_id=repo.id,
            kind="restore",
            category="restore",
            status="completed",
            trigger="manual",
            priority=0,
            run_id="run-list",
            params={"archive_name": "new"},
        )
        test_db.add_all([legacy, op])
        test_db.flush()
        restore_details(test_db, op).archive = "new"
        test_db.commit()

        response = test_client.get("/api/restore/jobs", headers=admin_headers)

        assert response.status_code == 200
        archives = {job["archive"] for job in response.json()["jobs"]}
        assert archives == {"old", "new"}

    def test_list_reads_each_operation_log_file_once(
        self, test_client: TestClient, admin_headers, test_db, tmp_path
    ):
        """The log lives in a file now, not on the row, so the list route has
        to read it once per job rather than once per use of it. Archives.tsx
        polls this route every three seconds at the default limit."""
        from app.services.operations.details import restore_details

        _set_log_save_policy(test_db, "all_jobs")
        repo = Repository(
            name="Restore Repo",
            path="/test/restore-repo",
            encryption="none",
            repository_type="local",
        )
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)
        reads: list[str] = []
        log_files = []
        for index in range(3):
            log_file = tmp_path / f"restore-{index}.log"
            log_file.write_text("extracted a file\n", encoding="utf-8")
            log_files.append(log_file)
            op = Operation(
                repository_id=repo.id,
                kind="restore",
                category="restore",
                status="completed",
                trigger="manual",
                priority=0,
                run_id=f"run-read-{index}",
                log_file_path=str(log_file),
                params={"archive_name": f"archive-{index}"},
            )
            test_db.add(op)
            test_db.flush()
            restore_details(test_db, op).archive = f"archive-{index}"
        test_db.commit()

        real_read_text = Path.read_text

        def counting_read_text(self, *args, **kwargs):
            reads.append(str(self))
            return real_read_text(self, *args, **kwargs)

        with patch.object(Path, "read_text", counting_read_text):
            response = test_client.get("/api/restore/jobs", headers=admin_headers)

        assert response.status_code == 200
        assert len(response.json()["jobs"]) == 3
        for log_file in log_files:
            assert reads.count(str(log_file)) == 1

    def test_cancel_running_operation_kills_the_process_and_flags_the_runner(
        self, test_client: TestClient, admin_headers, test_db
    ):
        from app.services.operations.restore_facade import CANCELLED_BY_USER

        repo = Repository(
            name="Restore Repo",
            path="/test/restore-repo",
            encryption="none",
            repository_type="local",
        )
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)
        op = Operation(
            repository_id=repo.id,
            kind="restore",
            category="restore",
            status="running",
            trigger="manual",
            priority=0,
            run_id="run-cancel",
        )
        test_db.add(op)
        test_db.commit()

        with (
            patch(
                "app.api.restore.operation_runner.request_cancel",
                new=AsyncMock(return_value=True),
            ) as request_cancel,
            patch(
                "app.api.restore.restore_service.cancel_restore",
                new=AsyncMock(return_value=True),
            ) as cancel_restore,
        ):
            response = test_client.post(
                f"/api/restore/cancel/{op.id}", headers=admin_headers
            )

        assert response.status_code == 200
        assert response.json()["process_terminated"] is True
        request_cancel.assert_awaited_once_with(op.id)
        cancel_restore.assert_awaited_once_with(op.id)
        test_db.expire_all()
        assert op.status == "cancelled"
        assert op.error_message == CANCELLED_BY_USER
        assert op.completed_at is not None


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

    def test_get_restore_job_status_nonexistent(
        self, test_client: TestClient, admin_headers
    ):
        """Test getting status of non-existent restore job"""
        response = test_client.get(
            "/api/restore/jobs/99999/status", headers=admin_headers
        )

        assert response.status_code == 404

    def test_get_restore_job_status_nonexistent_new_endpoint(
        self, test_client: TestClient, admin_headers
    ):
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
            "/api/restore/jobs/99999/cancel", headers=admin_headers
        )

        assert response.status_code == 405

    def test_cancel_restore_running_job_marks_cancelled(
        self,
        test_client: TestClient,
        admin_headers,
        test_db,
    ):
        repo = Repository(
            name="Restore Repo",
            path="/test/repo",
            encryption="none",
            repository_type="local",
        )
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

        with patch(
            "app.api.restore.restore_service.cancel_restore",
            new=AsyncMock(return_value=True),
        ) as mock_cancel:
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
        repo = Repository(
            name="Restore Repo",
            path="/test/repo-nonrunning",
            encryption="none",
            repository_type="local",
        )
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
        assert (
            response.json()["detail"]["key"]
            == "backend.errors.restore.canOnlyCancelRunningJobs"
        )

    def test_restore_logs_nonexistent_job(self, test_client: TestClient, admin_headers):
        """Test getting logs for non-existent restore job"""
        response = test_client.get(
            "/api/restore/jobs/99999/logs", headers=admin_headers
        )

        assert response.status_code == 404


@pytest.mark.unit
class TestRestoreSpeedAndETA:
    """Test restore speed and ETA tracking functionality"""

    def test_restore_job_includes_speed_and_eta_fields(
        self, test_client: TestClient, admin_headers, test_db
    ):
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
            restored_size=4767744,  # ~4.5 MB
            restore_speed=12.34,  # MB/s
            estimated_time_remaining=135,  # seconds
        )
        test_db.add(job)
        test_db.commit()
        test_db.refresh(job)

        # Get job status
        response = test_client.get(
            f"/api/restore/status/{job.id}", headers=admin_headers
        )

        assert response.status_code == 200
        data = response.json()

        # Verify speed and ETA are included
        assert "progress_details" in data
        progress = data["progress_details"]
        assert "restore_speed" in progress
        assert "estimated_time_remaining" in progress
        assert progress["restore_speed"] == 12.34
        assert progress["estimated_time_remaining"] == 135

    def test_restore_jobs_list_includes_speed_and_eta(
        self, test_client: TestClient, admin_headers, test_db
    ):
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
                "estimated_time_remaining": 240,
            },
            {
                "repository": "/test/repo2",
                "archive": "archive2",
                "destination": "/test/dest2",
                "status": "completed",
                "started_at": datetime.now(timezone.utc),
                "completed_at": datetime.now(timezone.utc),
                "restore_speed": 0.0,
                "estimated_time_remaining": 0,
            },
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

    def test_restore_speed_defaults_to_zero(
        self, test_client: TestClient, admin_headers, test_db
    ):
        """Test that restore speed defaults to 0.0 when not set"""
        from app.database.models import RestoreJob

        job = RestoreJob(
            repository="/test/repo",
            archive="test-archive",
            destination="/test/dest",
            status="pending",
        )
        test_db.add(job)
        test_db.commit()
        test_db.refresh(job)

        response = test_client.get(
            f"/api/restore/status/{job.id}", headers=admin_headers
        )

        assert response.status_code == 200
        data = response.json()
        progress = data["progress_details"]
        assert progress["restore_speed"] == 0.0
        assert progress["estimated_time_remaining"] == 0

    def test_restore_eta_zero_when_speed_zero(
        self, test_client: TestClient, admin_headers, test_db
    ):
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
            estimated_time_remaining=0,
        )
        test_db.add(job)
        test_db.commit()
        test_db.refresh(job)

        response = test_client.get(
            f"/api/restore/status/{job.id}", headers=admin_headers
        )

        assert response.status_code == 200
        data = response.json()
        progress = data["progress_details"]
        assert progress["estimated_time_remaining"] == 0

    def test_restore_completed_job_speed_preserved(
        self, test_client: TestClient, admin_headers, test_db
    ):
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
            progress_percent=100.0,
        )
        test_db.add(job)
        test_db.commit()
        test_db.refresh(job)

        response = test_client.get(
            f"/api/restore/status/{job.id}", headers=admin_headers
        )

        assert response.status_code == 200
        data = response.json()
        progress = data["progress_details"]
        assert progress["restore_speed"] == 18.92
        assert progress["estimated_time_remaining"] == 0
        assert data["status"] == "completed"


@pytest.mark.unit
class TestRestoreJobLogs:
    """Test restore job logs functionality"""

    def test_restore_jobs_list_includes_logs(
        self, test_client: TestClient, admin_headers, test_db
    ):
        """Test that /api/restore/jobs endpoint includes logs field"""
        from app.database.models import RestoreJob
        from datetime import datetime, timezone

        _set_log_save_policy(test_db, "all_jobs")
        job = RestoreJob(
            repository="/test/repo",
            archive="test-archive",
            destination="/test/dest",
            status="completed",
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
            logs="Test log line 1\nTest log line 2\nRestore completed",
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

    def test_restore_job_status_includes_logs(
        self, test_client: TestClient, admin_headers, test_db
    ):
        """Test that /api/restore/status/{id} endpoint includes logs field"""
        from app.database.models import RestoreJob
        from datetime import datetime, timezone

        _set_log_save_policy(test_db, "all_jobs")
        job = RestoreJob(
            repository="/test/repo",
            archive="test-archive",
            destination="/test/dest",
            status="completed",
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
            logs="Detailed restore logs here\nProgress: 100%\nSuccess",
        )
        test_db.add(job)
        test_db.commit()
        test_db.refresh(job)

        response = test_client.get(
            f"/api/restore/status/{job.id}", headers=admin_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert "logs" in data
        assert data["logs"] == job.logs

    def test_restore_logs_follow_log_save_policy(
        self, test_client: TestClient, admin_headers, test_db
    ):
        from datetime import datetime, timezone

        _set_log_save_policy(test_db, "failed_only")
        job = RestoreJob(
            repository="/test/repo",
            archive="test-archive",
            destination="/test/dest",
            status="completed",
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
            logs="successful restore log",
        )
        test_db.add(job)
        test_db.commit()
        test_db.refresh(job)

        jobs_response = test_client.get("/api/restore/jobs", headers=admin_headers)
        assert jobs_response.status_code == 200
        listed_job = next(
            item for item in jobs_response.json()["jobs"] if item["id"] == job.id
        )
        assert listed_job["logs"] is None

        status_response = test_client.get(
            f"/api/restore/status/{job.id}", headers=admin_headers
        )
        assert status_response.status_code == 200
        assert status_response.json()["logs"] is None

    def test_restore_jobs_with_null_logs(
        self, test_client: TestClient, admin_headers, test_db
    ):
        """Test that jobs with null logs return null in API"""
        from app.database.models import RestoreJob
        from datetime import datetime, timezone

        job = RestoreJob(
            repository="/test/repo",
            archive="test-archive",
            destination="/test/dest",
            status="running",
            started_at=datetime.now(timezone.utc),
            logs=None,  # No logs yet for running job
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

    def test_restore_jobs_with_empty_logs(
        self, test_client: TestClient, admin_headers, test_db
    ):
        """Test that jobs with empty string logs return empty string"""
        from app.database.models import RestoreJob
        from datetime import datetime, timezone

        _set_log_save_policy(test_db, "all_jobs")
        job = RestoreJob(
            repository="/test/repo",
            archive="test-archive",
            destination="/test/dest",
            status="completed",
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
            logs="",  # Empty logs
        )
        test_db.add(job)
        test_db.commit()
        test_db.refresh(job)

        response = test_client.get(
            f"/api/restore/status/{job.id}", headers=admin_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert "logs" in data
        assert data["logs"] == ""

    def test_restore_jobs_with_multiline_logs(
        self, test_client: TestClient, admin_headers, test_db
    ):
        """Test that multiline logs are preserved correctly"""
        from app.database.models import RestoreJob
        from datetime import datetime, timezone

        _set_log_save_policy(test_db, "all_jobs")
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
            logs=multiline_logs,
        )
        test_db.add(job)
        test_db.commit()
        test_db.refresh(job)

        response = test_client.get(
            f"/api/restore/status/{job.id}", headers=admin_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["logs"] == multiline_logs
        # Verify line breaks are preserved
        assert "\n" in data["logs"]
        assert data["logs"].count("\n") == multiline_logs.count("\n")


@pytest.mark.unit
class TestRestoreRequestShape:
    """The restore request model carries no dry-run switch. Dry-run restore is
    the dedicated preview route, which runs borg extract with --dry-run."""

    def test_restore_request_has_no_dry_run_field(self):
        from app.api.restore import RestoreRequest

        assert "dry_run" not in RestoreRequest.model_fields

    def test_start_ignores_a_dry_run_field_a_client_still_sends(
        self, test_client: TestClient, admin_headers, test_db
    ):
        """Pydantic ignores unknown fields, so a client still sending dry_run
        gets exactly the behaviour it got before the field was removed: a real
        restore, enqueued the same way, with nothing recorded about dry run."""
        repo = Repository(
            name="Dry Run Repo",
            path="/test/dry-run-repo",
            encryption="none",
            repository_type="local",
        )
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        with patch(
            "app.services.restore_service.restore_service.execute_restore",
            new=AsyncMock(return_value=None),
        ):
            response = test_client.post(
                "/api/restore/start",
                json={
                    "repository": repo.path,
                    "repository_id": repo.id,
                    "archive": "test-archive",
                    "paths": ["docs/"],
                    "destination": "/restore/target",
                    "dry_run": True,
                },
                headers=admin_headers,
            )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "pending"

        operation = test_db.get(Operation, body["job_id"])
        assert operation.kind == "restore"
        assert operation.repository_id == repo.id
        assert "dry_run" not in operation.params
