"""
Unit tests for activity API - log buffer functionality.
"""

import pytest
from app.services.backup_service import BackupService


class TestBackupServiceLogBuffer:
    """Test BackupService log buffer methods"""

    def test_get_log_buffer_returns_tail(self):
        """Test that get_log_buffer returns last N lines"""
        from app.services.backup_service import BackupService

        service = BackupService()

        # Create a mock buffer with 100 lines
        job_id = 123
        service.log_buffers[job_id] = [f"line {i}" for i in range(100)]

        # Get last 10 lines
        result, buffer_exists = service.get_log_buffer(job_id, tail_lines=10)

        assert buffer_exists is True
        assert len(result) == 10
        assert result[0] == "line 90"
        assert result[-1] == "line 99"

    def test_get_log_buffer_returns_all_if_smaller(self):
        """Test that get_log_buffer returns all lines if buffer is smaller than tail_lines"""
        from app.services.backup_service import BackupService

        service = BackupService()

        # Create a small buffer
        job_id = 456
        service.log_buffers[job_id] = ["line 1", "line 2", "line 3"]

        # Request 500 lines
        result, buffer_exists = service.get_log_buffer(job_id, tail_lines=500)

        assert buffer_exists is True
        assert len(result) == 3
        assert result == ["line 1", "line 2", "line 3"]

    def test_get_log_buffer_empty_for_nonexistent_job(self):
        """Test that get_log_buffer returns empty list and False for nonexistent job"""
        from app.services.backup_service import BackupService

        service = BackupService()

        # Request buffer for job that doesn't exist
        result, buffer_exists = service.get_log_buffer(999, tail_lines=500)

        assert buffer_exists is False
        assert result == []

    def test_get_log_buffer_exists_but_empty(self):
        """Test that get_log_buffer distinguishes between 'buffer exists but empty' vs 'buffer doesn't exist'"""
        from app.services.backup_service import BackupService

        service = BackupService()

        # Create an empty buffer (job started but no logs yet)
        job_id = 789
        service.log_buffers[job_id] = []

        # Request buffer
        result, buffer_exists = service.get_log_buffer(job_id, tail_lines=500)

        # Buffer exists (True) but is empty
        assert buffer_exists is True
        assert result == []
        assert len(result) == 0


@pytest.mark.unit
class TestDeleteJobEndpoint:
    """Test DELETE /api/activity/{job_type}/{job_id} endpoint"""

    def test_delete_backup_job_success_admin(self, test_client, admin_headers, test_db):
        """Test admin can successfully delete a completed backup job"""
        from app.database.models import BackupJob
        from datetime import datetime

        # Create a completed backup job
        job = BackupJob(
            repository="/test/repo",
            status="completed",
            started_at=datetime.now(),
            completed_at=datetime.now()
        )
        test_db.add(job)
        test_db.commit()
        test_db.refresh(job)
        job_id = job.id

        # Delete the job
        response = test_client.delete(
            f"/api/activity/backup/{job_id}",
            headers=admin_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["job_id"] == job_id
        assert data["job_type"] == "backup"
        assert "deleted successfully" in data["message"].lower()

        # Verify job is deleted from database
        deleted_job = test_db.query(BackupJob).filter(BackupJob.id == job_id).first()
        assert deleted_job is None

    def test_delete_job_non_admin_forbidden(self, test_client, auth_headers, test_db):
        """Test non-admin user cannot delete jobs"""
        from app.database.models import BackupJob
        from datetime import datetime

        # Create a completed backup job
        job = BackupJob(
            repository="/test/repo",
            status="completed",
            started_at=datetime.now(),
            completed_at=datetime.now()
        )
        test_db.add(job)
        test_db.commit()
        test_db.refresh(job)

        # Try to delete as non-admin
        response = test_client.delete(
            f"/api/activity/backup/{job.id}",
            headers=auth_headers
        )

        assert response.status_code == 401
        data = response.json()
        assert "admin" in data["detail"].lower()

        # Verify job is NOT deleted
        job_still_exists = test_db.query(BackupJob).filter(BackupJob.id == job.id).first()
        assert job_still_exists is not None

    def test_delete_running_job_fails(self, test_client, admin_headers, test_db):
        """Test cannot delete running job"""
        from app.database.models import BackupJob
        from datetime import datetime

        # Create a running backup job
        job = BackupJob(
            repository="/test/repo",
            status="running",
            started_at=datetime.now()
        )
        test_db.add(job)
        test_db.commit()
        test_db.refresh(job)

        # Try to delete running job
        response = test_client.delete(
            f"/api/activity/backup/{job.id}",
            headers=admin_headers
        )

        assert response.status_code == 400
        data = response.json()
        assert "running" in data["detail"].lower()

        # Verify job is NOT deleted
        job_still_exists = test_db.query(BackupJob).filter(BackupJob.id == job.id).first()
        assert job_still_exists is not None

    def test_delete_pending_job_succeeds(self, test_client, admin_headers, test_db):
        """Test can delete pending job (useful for cleaning up stuck jobs)"""
        from app.database.models import BackupJob
        from datetime import datetime

        # Create a pending backup job
        job = BackupJob(
            repository="/test/repo",
            status="pending",
            started_at=datetime.now()
        )
        test_db.add(job)
        test_db.commit()
        test_db.refresh(job)

        # Delete pending job (should succeed now)
        response = test_client.delete(
            f"/api/activity/backup/{job.id}",
            headers=admin_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Backup job deleted successfully"

        # Verify job IS deleted
        job_deleted = test_db.query(BackupJob).filter(BackupJob.id == job.id).first()
        assert job_deleted is None

    def test_delete_failed_job_success(self, test_client, admin_headers, test_db):
        """Test admin can delete failed job"""
        from app.database.models import BackupJob
        from datetime import datetime

        # Create a failed backup job
        job = BackupJob(
            repository="/test/repo",
            status="failed",
            started_at=datetime.now(),
            completed_at=datetime.now(),
            error_message="Backup failed"
        )
        test_db.add(job)
        test_db.commit()
        test_db.refresh(job)
        job_id = job.id

        # Delete the job
        response = test_client.delete(
            f"/api/activity/backup/{job_id}",
            headers=admin_headers
        )

        assert response.status_code == 200

        # Verify job is deleted
        deleted_job = test_db.query(BackupJob).filter(BackupJob.id == job_id).first()
        assert deleted_job is None

    def test_delete_nonexistent_job_fails(self, test_client, admin_headers):
        """Test deleting non-existent job returns 404"""
        response = test_client.delete(
            "/api/activity/backup/99999",
            headers=admin_headers
        )

        assert response.status_code == 404
        data = response.json()
        assert "not found" in data["detail"].lower()

    def test_delete_invalid_job_type(self, test_client, admin_headers):
        """Test deleting with invalid job type returns 400"""
        response = test_client.delete(
            "/api/activity/invalid_type/123",
            headers=admin_headers
        )

        assert response.status_code == 400
        data = response.json()
        assert "invalid job type" in data["detail"].lower()

    def test_delete_restore_job_success(self, test_client, admin_headers, test_db):
        """Test admin can delete completed restore job"""
        from app.database.models import RestoreJob
        from datetime import datetime

        # Create a completed restore job
        job = RestoreJob(
            repository="/test/repo",
            archive="test-archive",
            destination="/restore/path",
            status="completed",
            started_at=datetime.now(),
            completed_at=datetime.now()
        )
        test_db.add(job)
        test_db.commit()
        test_db.refresh(job)
        job_id = job.id

        # Delete the job
        response = test_client.delete(
            f"/api/activity/restore/{job_id}",
            headers=admin_headers
        )

        assert response.status_code == 200

        # Verify job is deleted
        deleted_job = test_db.query(RestoreJob).filter(RestoreJob.id == job_id).first()
        assert deleted_job is None

    def test_delete_check_job_success(self, test_client, admin_headers, test_db):
        """Test admin can delete completed check job"""
        from app.database.models import CheckJob
        from datetime import datetime

        # Create a completed check job
        job = CheckJob(
            repository_id=1,
            status="completed",
            started_at=datetime.now(),
            completed_at=datetime.now()
        )
        test_db.add(job)
        test_db.commit()
        test_db.refresh(job)
        job_id = job.id

        # Delete the job
        response = test_client.delete(
            f"/api/activity/check/{job_id}",
            headers=admin_headers
        )

        assert response.status_code == 200

        # Verify job is deleted
        deleted_job = test_db.query(CheckJob).filter(CheckJob.id == job_id).first()
        assert deleted_job is None

    def test_delete_compact_job_success(self, test_client, admin_headers, test_db):
        """Test admin can delete completed compact job"""
        from app.database.models import CompactJob
        from datetime import datetime

        # Create a completed compact job
        job = CompactJob(
            repository_id=1,
            status="completed",
            started_at=datetime.now(),
            completed_at=datetime.now()
        )
        test_db.add(job)
        test_db.commit()
        test_db.refresh(job)
        job_id = job.id

        # Delete the job
        response = test_client.delete(
            f"/api/activity/compact/{job_id}",
            headers=admin_headers
        )

        assert response.status_code == 200

        # Verify job is deleted
        deleted_job = test_db.query(CompactJob).filter(CompactJob.id == job_id).first()
        assert deleted_job is None

    def test_delete_prune_job_success(self, test_client, admin_headers, test_db):
        """Test admin can delete completed prune job"""
        from app.database.models import PruneJob
        from datetime import datetime

        # Create a completed prune job
        job = PruneJob(
            repository_id=1,
            status="completed",
            started_at=datetime.now(),
            completed_at=datetime.now()
        )
        test_db.add(job)
        test_db.commit()
        test_db.refresh(job)
        job_id = job.id

        # Delete the job
        response = test_client.delete(
            f"/api/activity/prune/{job_id}",
            headers=admin_headers
        )

        assert response.status_code == 200

        # Verify job is deleted
        deleted_job = test_db.query(PruneJob).filter(PruneJob.id == job_id).first()
        assert deleted_job is None

    def test_delete_job_with_log_file(self, test_client, admin_headers, test_db, tmp_path):
        """Test deleting job also deletes log file"""
        from app.database.models import BackupJob
        from datetime import datetime
        import os

        # Create a temporary log file
        log_file = tmp_path / "test_log.txt"
        log_file.write_text("Test log content")
        assert log_file.exists()

        # Create a completed backup job with log file
        job = BackupJob(
            repository="/test/repo",
            status="completed",
            started_at=datetime.now(),
            completed_at=datetime.now(),
            log_file_path=str(log_file)
        )
        test_db.add(job)
        test_db.commit()
        test_db.refresh(job)
        job_id = job.id

        # Delete the job
        response = test_client.delete(
            f"/api/activity/backup/{job_id}",
            headers=admin_headers
        )

        assert response.status_code == 200

        # Verify job is deleted
        deleted_job = test_db.query(BackupJob).filter(BackupJob.id == job_id).first()
        assert deleted_job is None

        # Verify log file is deleted
        assert not log_file.exists()

    def test_delete_cancelled_job_success(self, test_client, admin_headers, test_db):
        """Test admin can delete cancelled job"""
        from app.database.models import BackupJob
        from datetime import datetime

        # Create a cancelled backup job
        job = BackupJob(
            repository="/test/repo",
            status="cancelled",
            started_at=datetime.now(),
            completed_at=datetime.now()
        )
        test_db.add(job)
        test_db.commit()
        test_db.refresh(job)
        job_id = job.id

        # Delete the job
        response = test_client.delete(
            f"/api/activity/backup/{job_id}",
            headers=admin_headers
        )

        assert response.status_code == 200

        # Verify job is deleted
        deleted_job = test_db.query(BackupJob).filter(BackupJob.id == job_id).first()
        assert deleted_job is None

    def test_delete_job_unauthenticated(self, test_client, test_db):
        """Test deleting job without authentication fails"""
        from app.database.models import BackupJob
        from datetime import datetime

        # Create a completed backup job
        job = BackupJob(
            repository="/test/repo",
            status="completed",
            started_at=datetime.now(),
            completed_at=datetime.now()
        )
        test_db.add(job)
        test_db.commit()
        test_db.refresh(job)

        # Try to delete without auth
        response = test_client.delete(f"/api/activity/backup/{job.id}")

        assert response.status_code == 403  # FastAPI returns 403 for auth failures

        # Verify job is NOT deleted
        job_still_exists = test_db.query(BackupJob).filter(BackupJob.id == job.id).first()
        assert job_still_exists is not None
