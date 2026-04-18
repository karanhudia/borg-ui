import json
from datetime import datetime, timezone
from unittest.mock import patch, mock_open, MagicMock
from app.utils.datetime_utils import serialize_datetime
from app.utils.process_utils import (
    is_process_alive,
    break_repository_lock,
    cleanup_orphaned_jobs,
    cleanup_orphaned_mounts,
)
from app.database.models import Repository, BackupJob, PruneJob, CompactJob

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
            id=1, path="/tmp/repo", repository_type="local", passphrase="secret"
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
            remote_path="/usr/bin/borg",
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
        mock_backup_job.maintenance_status = "running_prune"

        mock_prune_job = MagicMock(spec=PruneJob)
        mock_prune_job.id = 2
        mock_prune_job.repository_id = 10
        mock_prune_job.repository_path = "repo1"

        mock_compact_job = MagicMock(spec=CompactJob)
        mock_compact_job.id = 3
        mock_compact_job.repository_id = 11
        mock_compact_job.repository_path = "repo2"
        mock_compact_job.process_pid = 123
        mock_compact_job.process_start_time = 456

        mock_compact_backup_job = MagicMock(spec=BackupJob)
        mock_compact_backup_job.id = 4
        mock_compact_backup_job.repository = "repo2"
        mock_compact_backup_job.maintenance_status = "running_compact"

        # Setup query chain
        query_results = [
            [mock_backup_job],  # running backup jobs
            [],  # running restore jobs
            [],  # running check jobs
            [mock_prune_job],  # running prune jobs
            [mock_compact_job],  # running compact jobs
            [mock_backup_job],  # backup jobs stuck in running_prune
            [],  # repository lookup for orphaned compact job
            [mock_compact_backup_job],  # backup jobs stuck in running_compact
        ]

        def build_query(result):
            mock_query = MagicMock()
            mock_query.filter.return_value = mock_query
            mock_query.all.return_value = result
            mock_query.first.return_value = None
            return mock_query

        mock_db.query.side_effect = [build_query(result) for result in query_results]

        # Execute
        with patch("app.utils.process_utils.is_process_alive", return_value=False):
            cleanup_orphaned_jobs(mock_db)

        # Verify backup job was marked failed
        assert mock_backup_job.status == "failed"
        assert (
            json.loads(mock_backup_job.error_message)["key"]
            == "backend.errors.service.containerRestartedDuringBackup"
        )
        assert mock_backup_job.completed_at is not None
        assert mock_backup_job.maintenance_status == "prune_failed"

        assert mock_prune_job.status == "failed"
        assert (
            json.loads(mock_prune_job.error_message)["key"]
            == "backend.errors.service.containerRestartedDuringOperation"
        )
        assert mock_prune_job.completed_at is not None

        assert mock_compact_job.status == "failed"
        assert (
            json.loads(mock_compact_job.error_message.split("\n")[0])["key"]
            == "backend.errors.service.containerRestartedDuringOperation"
        )
        assert mock_compact_job.completed_at is not None
        assert mock_compact_backup_job.maintenance_status == "compact_failed"

        # Verify commit was called
        mock_db.commit.assert_called_once()

    @patch("app.utils.process_utils.settings")
    @patch("app.utils.process_utils.subprocess.run")
    def test_cleanup_orphaned_mounts_handles_managed_mount_dir_names(
        self, mock_run, mock_settings, tmp_path
    ):
        managed_mount_base = tmp_path / "mounts"
        managed_mount_base.mkdir()
        orphaned_dir = managed_mount_base / "manual-backup-2026-01-15T16_24_12"
        orphaned_dir.mkdir()

        mock_settings.data_dir = str(tmp_path)
        mock_run.side_effect = [
            MagicMock(
                returncode=0,
                stdout=f"borgfs on {orphaned_dir} type fuse.borgfs (rw,nosuid,nodev,relatime,user_id=0,group_id=0)",
            ),
            MagicMock(returncode=0, stderr=""),
        ]

        cleanup_orphaned_mounts()

        assert not orphaned_dir.exists()
        assert mock_run.call_args_list[1][0][0] == [
            "fusermount",
            "-uz",
            str(orphaned_dir),
        ]
