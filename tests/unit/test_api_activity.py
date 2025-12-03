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
        result = service.get_log_buffer(job_id, tail_lines=10)

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
        result = service.get_log_buffer(job_id, tail_lines=500)

        assert len(result) == 3
        assert result == ["line 1", "line 2", "line 3"]

    def test_get_log_buffer_empty_for_nonexistent_job(self):
        """Test that get_log_buffer returns empty list for nonexistent job"""
        from app.services.backup_service import BackupService

        service = BackupService()

        # Request buffer for job that doesn't exist
        result = service.get_log_buffer(999, tail_lines=500)

        assert result == []
