"""
Unit tests for Log Manager Service

Tests log storage calculations, cleanup operations, and file management.
"""

import pytest
import os
import tempfile
import time
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock

from app.services.log_manager import LogManager, log_manager
from app.database.models import BackupJob, RestoreJob, CheckJob, CompactJob, PruneJob, PackageInstallJob


@pytest.fixture
def temp_log_dir():
    """Create temporary log directory for testing"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def log_manager_with_temp_dir(temp_log_dir):
    """Create LogManager instance with temporary directory"""
    manager = LogManager()
    manager.log_dir = temp_log_dir
    return manager


@pytest.fixture
def create_test_log_file(temp_log_dir):
    """Helper fixture to create test log files"""
    def _create(name: str, content: str = "test log", age_days: int = 0):
        filepath = temp_log_dir / name
        filepath.write_text(content)

        # Set mtime if age_days specified
        if age_days > 0:
            old_time = (datetime.now() - timedelta(days=age_days)).timestamp()
            os.utime(filepath, (old_time, old_time))

        return filepath

    return _create


class TestCalculateLogStorage:
    """Test log storage calculation"""

    def test_empty_directory(self, log_manager_with_temp_dir):
        """Should return zeros for empty directory"""
        result = log_manager_with_temp_dir.calculate_log_storage()

        assert result["total_size_bytes"] == 0
        assert result["total_size_mb"] == 0.0
        assert result["file_count"] == 0
        assert result["oldest_log_date"] is None
        assert result["newest_log_date"] is None
        assert all(count == 0 for count in result["files_by_type"].values())

    def test_single_log_file(self, log_manager_with_temp_dir, create_test_log_file):
        """Should calculate size for single log file"""
        content = "test log content" * 100  # ~1600 bytes
        create_test_log_file("backup_job_1_20240101.log", content)

        result = log_manager_with_temp_dir.calculate_log_storage()

        assert result["file_count"] == 1
        assert result["total_size_bytes"] > 0
        assert result["total_size_mb"] >= 0  # Small files may round to 0.0 MB
        assert result["oldest_log_date"] is not None
        assert result["newest_log_date"] is not None
        assert result["files_by_type"]["backup"] == 1

    def test_multiple_log_files_different_types(self, log_manager_with_temp_dir, create_test_log_file):
        """Should count files by type correctly"""
        create_test_log_file("backup_job_1.log", "backup")
        create_test_log_file("backup_job_2.log", "backup")
        create_test_log_file("restore_job_1.log", "restore")
        create_test_log_file("check_job_1.log", "check")
        create_test_log_file("compact_job_1.log", "compact")
        create_test_log_file("prune_job_1.log", "prune")
        create_test_log_file("package_job_1.log", "package")

        result = log_manager_with_temp_dir.calculate_log_storage()

        assert result["file_count"] == 7
        assert result["files_by_type"]["backup"] == 2
        assert result["files_by_type"]["restore"] == 1
        assert result["files_by_type"]["check"] == 1
        assert result["files_by_type"]["compact"] == 1
        assert result["files_by_type"]["prune"] == 1
        assert result["files_by_type"]["package"] == 1

    def test_ignores_non_log_files(self, log_manager_with_temp_dir, temp_log_dir):
        """Should ignore files without .log extension"""
        (temp_log_dir / "backup_job_1.log").write_text("log file")
        (temp_log_dir / "backup_job_2.txt").write_text("text file")
        (temp_log_dir / "README.md").write_text("readme")

        result = log_manager_with_temp_dir.calculate_log_storage()

        assert result["file_count"] == 1

    def test_oldest_newest_dates(self, log_manager_with_temp_dir, create_test_log_file):
        """Should correctly identify oldest and newest logs"""
        create_test_log_file("old.log", age_days=10)
        time.sleep(0.01)  # Ensure different mtimes
        create_test_log_file("medium.log", age_days=5)
        time.sleep(0.01)
        create_test_log_file("new.log", age_days=1)

        result = log_manager_with_temp_dir.calculate_log_storage()

        oldest = result["oldest_log_date"]
        newest = result["newest_log_date"]

        assert oldest < newest
        assert (datetime.now() - oldest).days >= 9  # ~10 days old
        assert (datetime.now() - newest).days >= 0  # ~1 day old


class TestGetRunningJobLogPaths:
    """Test getting protected log paths for running jobs"""

    def test_no_running_jobs(self, log_manager_with_temp_dir):
        """Should return empty set when no jobs are running"""
        mock_db = Mock()
        mock_db.query.return_value.filter.return_value.all.return_value = []

        result = log_manager_with_temp_dir.get_running_job_log_paths(mock_db)

        assert result == set()

    def test_running_backup_job(self, log_manager_with_temp_dir):
        """Should return log path for running backup job"""
        mock_db = Mock()

        running_backup = Mock(spec=BackupJob)
        running_backup.log_file_path = "/data/logs/backup_job_1.log"
        running_backup.status = "running"

        # Mock query chain
        def mock_query(model):
            query_mock = Mock()
            if model == BackupJob:
                query_mock.filter.return_value.all.return_value = [running_backup]
            else:
                query_mock.filter.return_value.all.return_value = []
            return query_mock

        mock_db.query = mock_query

        result = log_manager_with_temp_dir.get_running_job_log_paths(mock_db)

        assert "/data/logs/backup_job_1.log" in result

    def test_multiple_running_jobs(self, log_manager_with_temp_dir):
        """Should return all running job log paths"""
        mock_db = Mock()

        running_backup = Mock(spec=BackupJob)
        running_backup.log_file_path = "/data/logs/backup_job_1.log"

        running_restore = Mock(spec=RestoreJob)
        running_restore.log_file_path = "/data/logs/restore_job_1.log"

        def mock_query(model):
            query_mock = Mock()
            if model == BackupJob:
                query_mock.filter.return_value.all.return_value = [running_backup]
            elif model == RestoreJob:
                query_mock.filter.return_value.all.return_value = [running_restore]
            else:
                query_mock.filter.return_value.all.return_value = []
            return query_mock

        mock_db.query = mock_query

        result = log_manager_with_temp_dir.get_running_job_log_paths(mock_db)

        assert len(result) == 2
        assert "/data/logs/backup_job_1.log" in result
        assert "/data/logs/restore_job_1.log" in result

    def test_job_without_log_path(self, log_manager_with_temp_dir):
        """Should handle jobs without log_file_path attribute"""
        mock_db = Mock()

        running_job = Mock(spec=BackupJob)
        running_job.log_file_path = None  # No log file

        def mock_query(model):
            query_mock = Mock()
            if model == BackupJob:
                query_mock.filter.return_value.all.return_value = [running_job]
            else:
                query_mock.filter.return_value.all.return_value = []
            return query_mock

        mock_db.query = mock_query

        result = log_manager_with_temp_dir.get_running_job_log_paths(mock_db)

        assert result == set()


class TestCleanupLogsByAge:
    """Test age-based log cleanup"""

    def test_delete_old_logs(self, log_manager_with_temp_dir, create_test_log_file):
        """Should delete logs older than max_age_days"""
        old_log = create_test_log_file("old_log.log", age_days=40)
        recent_log = create_test_log_file("recent_log.log", age_days=10)

        result = log_manager_with_temp_dir.cleanup_logs_by_age(
            max_age_days=30,
            protected_paths=set()
        )

        assert result["deleted_count"] == 1
        assert result["skipped_count"] == 0
        assert result["deleted_size_mb"] >= 0

        # Verify old log was deleted and recent log was kept
        assert not old_log.exists(), "Old log should be deleted"
        assert recent_log.exists(), "Recent log should be kept"

    def test_keep_recent_logs(self, log_manager_with_temp_dir, create_test_log_file):
        """Should keep logs newer than max_age_days"""
        create_test_log_file("log1.log", age_days=5)
        create_test_log_file("log2.log", age_days=10)
        create_test_log_file("log3.log", age_days=20)

        result = log_manager_with_temp_dir.cleanup_logs_by_age(
            max_age_days=30,
            protected_paths=set()
        )

        assert result["deleted_count"] == 0
        assert len(list(log_manager_with_temp_dir.log_dir.glob("*.log"))) == 3

    def test_protect_running_job_logs(self, log_manager_with_temp_dir, create_test_log_file):
        """Should skip deletion of protected logs"""
        old_log = create_test_log_file("old_log.log", age_days=40)
        protected_log = create_test_log_file("protected_log.log", age_days=40)

        result = log_manager_with_temp_dir.cleanup_logs_by_age(
            max_age_days=30,
            protected_paths={str(protected_log)}
        )

        assert result["deleted_count"] == 1
        assert result["skipped_count"] == 1

        # Protected log should still exist
        assert not old_log.exists()
        assert protected_log.exists()

    def test_dry_run_mode(self, log_manager_with_temp_dir, create_test_log_file):
        """Should not delete files in dry run mode"""
        create_test_log_file("old_log.log", age_days=40)

        result = log_manager_with_temp_dir.cleanup_logs_by_age(
            max_age_days=30,
            protected_paths=set(),
            dry_run=True
        )

        assert result["deleted_count"] == 1
        # File should still exist
        assert (log_manager_with_temp_dir.log_dir / "old_log.log").exists()


class TestCleanupLogsBySize:
    """Test size-based log cleanup"""

    def test_cleanup_when_under_limit(self, log_manager_with_temp_dir, create_test_log_file):
        """Should not delete anything when under limit"""
        create_test_log_file("log1.log", "small content")

        result = log_manager_with_temp_dir.cleanup_logs_by_size(
            max_total_size_mb=10,
            protected_paths=set()
        )

        assert result["deleted_count"] == 0
        assert result["final_size_mb"] < 10

    def test_cleanup_when_over_limit(self, log_manager_with_temp_dir, create_test_log_file):
        """Should delete oldest logs when over limit"""
        # Create files with substantial content
        large_content = "X" * (1024 * 1024)  # 1 MB

        create_test_log_file("old.log", large_content, age_days=10)
        time.sleep(0.01)
        create_test_log_file("medium.log", large_content, age_days=5)
        time.sleep(0.01)
        create_test_log_file("new.log", large_content, age_days=1)

        # Set limit to 2 MB (should delete oldest file)
        result = log_manager_with_temp_dir.cleanup_logs_by_size(
            max_total_size_mb=2,
            protected_paths=set()
        )

        assert result["deleted_count"] > 0
        assert result["final_size_mb"] <= 2.0

        # Oldest file should be deleted
        assert not (log_manager_with_temp_dir.log_dir / "old.log").exists()

    def test_protect_running_jobs_size_cleanup(self, log_manager_with_temp_dir, create_test_log_file):
        """Should skip protected logs during size cleanup"""
        large_content = "X" * (1024 * 1024)  # 1 MB

        old_log = create_test_log_file("old.log", large_content, age_days=10)
        time.sleep(0.01)  # Ensure different mtimes
        protected_log = create_test_log_file("protected.log", large_content, age_days=5)

        result = log_manager_with_temp_dir.cleanup_logs_by_size(
            max_total_size_mb=1,  # Very small limit - should trigger cleanup
            protected_paths={str(protected_log)}
        )

        # Should attempt to delete old.log and skip protected.log
        # If protected.log is older by mtime, it might be skipped
        # If old.log is older, it should be deleted
        assert protected_log.exists(), "Protected log should not be deleted"

        # Either old.log was deleted OR protected.log was skipped (or both)
        assert result["deleted_count"] >= 0
        if not old_log.exists():
            # old.log was deleted
            assert result["deleted_count"] >= 1
        if protected_log.exists() and result["deleted_count"] == 0:
            # Nothing was deleted because protected.log couldn't be deleted
            assert result["skipped_count"] >= 1


class TestCleanupLogsCombined:
    """Test combined cleanup (age + size)"""

    def test_combined_cleanup(self, log_manager_with_temp_dir, create_test_log_file):
        """Should perform both age and size cleanup"""
        mock_db = Mock()
        mock_db.query.return_value.filter.return_value.all.return_value = []

        large_content = "X" * (1024 * 1024)  # 1 MB

        # Create old log (should be deleted by age)
        create_test_log_file("very_old.log", large_content, age_days=40)

        # Create recent but large logs (should be deleted by size)
        create_test_log_file("log1.log", large_content, age_days=5)
        create_test_log_file("log2.log", large_content, age_days=3)
        create_test_log_file("log3.log", large_content, age_days=1)

        result = log_manager_with_temp_dir.cleanup_logs_combined(
            db=mock_db,
            max_age_days=30,
            max_total_size_mb=2,  # Should trigger size cleanup
            dry_run=False
        )

        assert result["total_deleted_count"] > 0
        assert result["age_cleanup"]["deleted_count"] >= 1  # very_old.log
        assert result["success"] is True

    def test_combined_cleanup_respects_protected_paths(self, log_manager_with_temp_dir, create_test_log_file):
        """Should protect running job logs in combined cleanup"""
        large_content = "X" * (1024 * 1024)  # 1 MB

        # Create running job
        running_job = Mock(spec=BackupJob)
        protected_log = create_test_log_file("running.log", large_content, age_days=40)
        running_job.log_file_path = str(protected_log)

        mock_db = Mock()

        def mock_query(model):
            query_mock = Mock()
            if model == BackupJob:
                query_mock.filter.return_value.all.return_value = [running_job]
            else:
                query_mock.filter.return_value.all.return_value = []
            return query_mock

        mock_db.query = mock_query

        # Create non-protected old log
        create_test_log_file("old.log", large_content, age_days=40)

        result = log_manager_with_temp_dir.cleanup_logs_combined(
            db=mock_db,
            max_age_days=30,
            max_total_size_mb=10,
            dry_run=False
        )

        # Old.log should be deleted, but running.log should be protected
        assert not (log_manager_with_temp_dir.log_dir / "old.log").exists()
        assert protected_log.exists()

        # Should have skipped the protected log
        total_skipped = (result["age_cleanup"]["skipped_count"] +
                        result["size_cleanup"]["skipped_count"])
        assert total_skipped >= 1


class TestGlobalLogManagerInstance:
    """Test global log_manager instance"""

    def test_global_instance_exists(self):
        """Should have a global log_manager instance"""
        from app.services.log_manager import log_manager

        assert log_manager is not None
        assert isinstance(log_manager, LogManager)

    def test_log_dir_created(self):
        """Should create log directory on initialization"""
        # The global instance should have created the log directory
        assert log_manager.log_dir.exists()
        assert log_manager.log_dir.is_dir()
