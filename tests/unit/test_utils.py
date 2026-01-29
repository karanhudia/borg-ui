import pytest
from datetime import datetime, timezone
from unittest.mock import Mock, patch, mock_open, MagicMock
from app.utils.datetime_utils import serialize_datetime
from app.utils.process_utils import is_process_alive, break_repository_lock, cleanup_orphaned_jobs
from app.database.models import Repository, BackupJob

# ==========================================
# Datetime Utils Tests
# ==========================================

class TestDatetimeUtils:
    def test_serialize_none(self):
        """Test serializing None returns None"""
        assert serialize_datetime(None) is None

    def test_serialize_naive_datetime(self):
        """Test naive datetime (DB format) is treated as UTC"""
        dt = datetime(2025, 1, 1, 12, 0, 0)  # Naive
        serialized = serialize_datetime(dt)
        assert serialized == "2025-01-01T12:00:00+00:00"

    def test_serialize_aware_datetime(self):
        """Test aware datetime is converted to UTC"""
        # Let's use a manual offset for clarity +01:00
        from datetime import timedelta
        tz_plus_1 = timezone(timedelta(hours=1))

        dt = datetime(2025, 1, 1, 13, 0, 0, tzinfo=tz_plus_1)
        serialized = serialize_datetime(dt)
        # 13:00 +01:00 is 12:00 UTC
        assert serialized == "2025-01-01T12:00:00+00:00"

# ==========================================
# Process Utils Tests
# ==========================================

class TestProcessUtils:
    def test_is_process_alive_no_pid(self):
        """Test returns False for invalid inputs"""
        assert is_process_alive(None, 123) is False
        assert is_process_alive(123, None) is False

    @patch("builtins.open", new_callable=mock_open)
    def test_is_process_alive_success(self, mock_file):
        """Test active process detection"""
        # Format of /proc/pid/stat: pid (name) state ppid ... starttime (22nd field, index 21)
        # util.py: fields = stat_data.split(')')[1].split()
        #          current_start_time = int(fields[19])
        # fields[0] is state (field 3). fields[19] is field 22.
        # We need 19 fields before start_time (indices 0-18)

        # Create mock content with enough fields
        # 19 fields of padding to make starttime index 19
        padding = " ".join(["0"] * 19)
        # Start time is 1000
        content = f"123 (test) {padding} 1000 0 0"

        mock_file.return_value.read.return_value = content

        # Should return True if start times match
        assert is_process_alive(123, 1000) is True

    @patch("builtins.open", side_effect=FileNotFoundError)
    def test_is_process_alive_not_found(self, mock_file):
        """Test process not found"""
        assert is_process_alive(123, 1000) is False

    @patch("builtins.open", new_callable=mock_open)
    def test_is_process_alive_pid_reused(self, mock_file):
        """Test PID reuse detection"""
        # Mock content with DIFFERENT start time (2000 vs 1000)
        padding = " ".join(["0"] * 19)
        content = f"123 (test) {padding} 2000 0 0"
        mock_file.return_value.read.return_value = content

        assert is_process_alive(123, 1000) is False

    @patch("subprocess.run")
    def test_break_repository_lock_local_success(self, mock_run):
        """Test breaking lock for local repo"""
        repo = Repository(
            id=1,
            path="/tmp/repo",
            repository_type="local",
            passphrase="secret"
        )

        mock_run.return_value.returncode = 0

        assert break_repository_lock(repo) is True

        # Verify command
        args = mock_run.call_args[0][0]
        assert args == ["borg", "break-lock", "/tmp/repo"]

        # Verify env
        env = mock_run.call_args[1]["env"]
        assert env["BORG_PASSPHRASE"] == "secret"

    @patch("subprocess.run")
    def test_break_repository_lock_ssh_success(self, mock_run):
        """Test breaking lock for SSH repo"""
        repo = Repository(
            id=1,
            path="ssh://user@host/repo",
            connection_id=1,  # SSH repo has connection_id
            remote_path="/usr/bin/borg"
        )

        mock_run.return_value.returncode = 0

        assert break_repository_lock(repo) is True

        # Verify command includes remote-path
        args = mock_run.call_args[0][0]
        assert "--remote-path" in args
        assert "/usr/bin/borg" in args

        # Verify SSH setup
        env = mock_run.call_args[1]["env"]
        assert "BORG_RSH" in env
        assert "ssh -o StrictHostKeyChecking=no" in env["BORG_RSH"]

    def test_cleanup_orphaned_jobs(self):
        """Test cleanup of orphaned jobs"""
        # Create mock session
        mock_db = MagicMock()

        # Setup mock jobs
        mock_backup_job = MagicMock(spec=BackupJob)
        mock_backup_job.id = 1
        mock_backup_job.repository = "repo1"

        # Setup query chain
        # db.query(Model).filter(...).all()
        # We need to handle multiple queries for different job types

        # Mock the query method to return a mock query object
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query

        # Configure .all() to return our jobs ONLY for BackupJob query
        # This is simplified; in a real scenario we'd check the model passed to query()
        # But for this test, returning [job] for the first call (backup) and [] for others works
        mock_query.all.side_effect = [
            [mock_backup_job], # BackupJob
            [], # RestoreJob
            [], # CheckJob
            [], # CompactJob
        ]

        # Execute
        cleanup_orphaned_jobs(mock_db)

        # Verify backup job was marked failed
        assert mock_backup_job.status == "failed"
        assert "Container restarted" in mock_backup_job.error_message
        assert mock_backup_job.completed_at is not None

        # Verify commit was called
        mock_db.commit.assert_called_once()
