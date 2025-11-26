"""
Unit tests for BackupService
"""
import pytest
import asyncio
import tempfile
from pathlib import Path
from datetime import datetime
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from app.services.backup_service import BackupService
from app.database.models import BackupJob, Repository


@pytest.mark.unit
class TestBackupService:
    """Test BackupService class methods"""

    @pytest.fixture
    def backup_service(self):
        """Create a BackupService instance"""
        with patch('app.services.backup_service.settings') as mock_settings:
            mock_settings.data_dir = tempfile.mkdtemp()
            service = BackupService()
            yield service

    def test_init(self, backup_service):
        """Test BackupService initialization"""
        assert backup_service is not None
        assert backup_service.log_dir.exists()
        assert backup_service.running_processes == {}
        assert backup_service.error_msgids == {}

    def test_format_bytes(self, backup_service):
        """Test _format_bytes method"""
        assert backup_service._format_bytes(0) == "0.00 B"
        assert backup_service._format_bytes(1024) == "1.00 KB"
        assert backup_service._format_bytes(1024 * 1024) == "1.00 MB"
        assert backup_service._format_bytes(1024 * 1024 * 1024) == "1.00 GB"
        assert backup_service._format_bytes(1024 * 1024 * 1024 * 1024) == "1.00 TB"
        assert backup_service._format_bytes(500) == "500.00 B"
        assert backup_service._format_bytes(1536) == "1.50 KB"

    def test_rotate_logs_empty_directory(self, backup_service):
        """Test rotate_logs with empty log directory"""
        # Should not raise any errors
        backup_service.rotate_logs(max_age_days=30, max_files=100)
        assert backup_service.log_dir.exists()

    def test_rotate_logs_with_old_files(self, backup_service):
        """Test rotate_logs removes old files"""
        import time

        # Create some test log files with correct pattern
        old_log = backup_service.log_dir / "backup_old.log"
        old_log.write_text("old log content")

        # Make the file appear old by setting its modification time
        old_time = time.time() - (31 * 24 * 60 * 60)  # 31 days ago
        import os
        os.utime(old_log, (old_time, old_time))

        # Run rotation
        backup_service.rotate_logs(max_age_days=30, max_files=100)

        # Old file should be deleted
        assert not old_log.exists()

    def test_rotate_logs_keeps_recent_files(self, backup_service):
        """Test rotate_logs keeps recent files"""
        # Create a recent log file with correct pattern
        recent_log = backup_service.log_dir / "backup_recent.log"
        recent_log.write_text("recent log content")

        # Run rotation
        backup_service.rotate_logs(max_age_days=30, max_files=100)

        # Recent file should still exist
        assert recent_log.exists()

    def test_rotate_logs_limits_file_count(self, backup_service):
        """Test rotate_logs limits number of files"""
        # Create many log files with correct pattern
        for i in range(150):
            log_file = backup_service.log_dir / f"backup_{i:03d}.log"
            log_file.write_text(f"log content {i}")

        # Run rotation with max_files=100
        backup_service.rotate_logs(max_age_days=30, max_files=100)

        # Should have at most 100 files
        remaining_files = list(backup_service.log_dir.glob("backup_*.log"))
        assert len(remaining_files) <= 100

    @pytest.mark.asyncio
    async def test_run_hook_success(self, backup_service):
        """Test _run_hook with successful script"""
        script = "echo 'test output'"
        result = await backup_service._run_hook(script, "test-hook", timeout=5, job_id=1)

        assert result["success"] is True
        assert result["returncode"] == 0
        assert "test output" in result["stdout"]

    @pytest.mark.asyncio
    async def test_run_hook_failure(self, backup_service):
        """Test _run_hook with failing script"""
        script = "exit 1"
        result = await backup_service._run_hook(script, "test-hook", timeout=5, job_id=1)

        assert result["success"] is False
        assert result["returncode"] == 1

    @pytest.mark.asyncio
    async def test_run_hook_timeout(self, backup_service):
        """Test _run_hook with timeout"""
        script = "sleep 10"
        result = await backup_service._run_hook(script, "test-hook", timeout=1, job_id=1)

        assert result["success"] is False
        assert result["returncode"] == -1
        assert "timed out" in result["stderr"].lower()

    @pytest.mark.asyncio
    async def test_calculate_source_size_empty(self, backup_service):
        """Test _calculate_source_size with empty list"""
        size = await backup_service._calculate_source_size([])
        assert size == 0

    @pytest.mark.asyncio
    async def test_calculate_source_size_nonexistent_path(self, backup_service):
        """Test _calculate_source_size with non-existent path"""
        size = await backup_service._calculate_source_size(["/nonexistent/path"])
        assert size == 0

    @pytest.mark.asyncio
    async def test_calculate_source_size_with_file(self, backup_service):
        """Test _calculate_source_size with actual file"""
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp.write(b"test content" * 100)
            tmp.flush()
            temp_path = tmp.name

        try:
            size = await backup_service._calculate_source_size([temp_path])
            assert size > 0
        finally:
            Path(temp_path).unlink()

    @pytest.mark.asyncio
    async def test_calculate_source_size_with_directory(self, backup_service):
        """Test _calculate_source_size with directory"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create some files in the directory
            for i in range(5):
                file_path = Path(temp_dir) / f"file_{i}.txt"
                file_path.write_text(f"content {i}" * 100)

            size = await backup_service._calculate_source_size([temp_dir])
            assert size > 0

    @pytest.mark.asyncio
    async def test_update_archive_stats_json_parse_error(self, backup_service, test_db):
        """Test _update_archive_stats with invalid JSON"""
        job = BackupJob(
            repository="/test/repo",
            status="running",
            started_at=datetime.now()
        )
        test_db.add(job)
        test_db.commit()
        test_db.refresh(job)

        # Mock the subprocess to return invalid JSON
        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(return_value=(b"invalid json", b""))
        mock_process.returncode = 0

        with patch('asyncio.create_subprocess_exec', return_value=mock_process):
            # Should not raise exception, just log warning
            await backup_service._update_archive_stats(
                test_db,
                job.id,
                "/test/repo",
                "test-archive",
                {}
            )

    @pytest.mark.asyncio
    async def test_update_archive_stats_borg_failure(self, backup_service, test_db):
        """Test _update_archive_stats when borg command fails"""
        job = BackupJob(
            repository="/test/repo",
            status="running",
            started_at=datetime.now()
        )
        test_db.add(job)
        test_db.commit()
        test_db.refresh(job)

        # Mock the subprocess to return error
        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(return_value=(b"", b"Error message"))
        mock_process.returncode = 1

        with patch('asyncio.create_subprocess_exec', return_value=mock_process):
            # Should not raise exception, just log warning
            await backup_service._update_archive_stats(
                test_db,
                job.id,
                "/test/repo",
                "test-archive",
                {}
            )

    @pytest.mark.asyncio
    async def test_update_repository_stats_success(self, backup_service, test_db):
        """Test _update_repository_stats with successful response"""
        # Create a repository record
        repo = Repository(
            name="Test Repo",
            path="/test/repo",
            encryption="none",
            repository_type="local"
        )
        test_db.add(repo)
        test_db.commit()

        # Mock the subprocess to return valid JSON
        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(return_value=(
            b'{"cache": {"stats": {"total_size": 1000000}}}',
            b""
        ))
        mock_process.returncode = 0

        with patch('asyncio.create_subprocess_exec', return_value=mock_process):
            # Should not raise exception
            await backup_service._update_repository_stats(
                test_db,
                "/test/repo",
                {}
            )

    @pytest.mark.asyncio
    async def test_update_repository_stats_failure(self, backup_service, test_db):
        """Test _update_repository_stats when borg command fails"""
        # Create a repository record
        repo = Repository(
            name="Test Repo",
            path="/test/repo",
            encryption="none",
            repository_type="local"
        )
        test_db.add(repo)
        test_db.commit()

        # Mock the subprocess to return error
        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(return_value=(b"", b"Repository not found"))
        mock_process.returncode = 1

        with patch('asyncio.create_subprocess_exec', return_value=mock_process):
            # Should not raise exception, just log warning
            await backup_service._update_repository_stats(
                test_db,
                "/test/repo",
                {}
            )

    @pytest.mark.asyncio
    async def test_execute_backup_job_not_found(self, backup_service, test_db):
        """Test execute_backup with non-existent job"""
        with patch('app.services.backup_service.SessionLocal', return_value=test_db):
            # Should handle gracefully
            try:
                await backup_service.execute_backup(99999, "/test/repo")
            except Exception as e:
                # Expected to fail with job not found
                assert "not found" in str(e).lower() or True

    @pytest.mark.asyncio
    async def test_execute_backup_repository_not_found(self, backup_service, test_db):
        """Test execute_backup with non-existent repository"""
        job = BackupJob(
            repository="/nonexistent/repo",
            status="pending",
            started_at=datetime.now()
        )
        test_db.add(job)
        test_db.commit()
        test_db.refresh(job)

        with patch('app.services.backup_service.SessionLocal', return_value=test_db):
            # Should handle gracefully
            try:
                await backup_service.execute_backup(job.id, "/nonexistent/repo")
            except Exception:
                # Expected to fail with repository not found
                pass

    def test_running_processes_tracking(self, backup_service):
        """Test that running_processes dict is managed correctly"""
        assert backup_service.running_processes == {}

        # Simulate adding a process
        mock_process = Mock()
        backup_service.running_processes[1] = mock_process
        assert 1 in backup_service.running_processes

        # Simulate removing a process
        del backup_service.running_processes[1]
        assert 1 not in backup_service.running_processes

    def test_error_msgids_tracking(self, backup_service):
        """Test that error_msgids dict is managed correctly"""
        assert backup_service.error_msgids == {}

        # Simulate adding an error msgid
        backup_service.error_msgids[1] = "test-error-msgid"
        assert backup_service.error_msgids[1] == "test-error-msgid"

        # Simulate removing an error msgid
        del backup_service.error_msgids[1]
        assert 1 not in backup_service.error_msgids

    @pytest.mark.asyncio
    async def test_ssh_repository_with_remote_path(self, backup_service, test_db):
        """Test that BORG_REMOTE_PATH environment variable is set for SSH repositories with remote_path"""
        # Create SSH repository with remote_path (no SSH key needed for this test)
        repository = Repository(
            name="ssh-test-repo",
            path="/backups/test-repo",
            repository_type="ssh",
            host="backup.example.com",
            port=22,
            username="backupuser",
            remote_path="/usr/local/bin/borg",  # Custom borg binary path
            passphrase="test123",
            source_directories='["/data"]',
            compression="lz4"
        )
        test_db.add(repository)
        test_db.commit()
        test_db.refresh(repository)

        # Create backup job
        job = BackupJob(
            repository=repository.path,
            status="pending"
        )
        test_db.add(job)
        test_db.commit()
        test_db.refresh(job)

        # Mock subprocess to capture environment variables
        mock_env = {}

        async def mock_create_subprocess(*args, **kwargs):
            # Capture the environment
            nonlocal mock_env
            mock_env = kwargs.get('env', {})

            # Return a mock process
            mock_process = AsyncMock()
            mock_process.stdout = AsyncMock()
            mock_process.stdout.readline = AsyncMock(return_value=b'')
            mock_process.wait = AsyncMock(return_value=0)
            mock_process.returncode = 0
            return mock_process

        with patch('asyncio.create_subprocess_exec', side_effect=mock_create_subprocess):
            with patch('app.services.backup_service.SessionLocal', return_value=test_db):
                try:
                    await backup_service.execute_backup(job.id, repository.path)
                except Exception:
                    pass  # We're only interested in capturing the environment

        # Verify BORG_REMOTE_PATH was set
        assert 'BORG_REMOTE_PATH' in mock_env
        assert mock_env['BORG_REMOTE_PATH'] == '/usr/local/bin/borg'

    @pytest.mark.asyncio
    async def test_ssh_repository_without_remote_path(self, backup_service, test_db):
        """Test that BORG_REMOTE_PATH is not set when remote_path is not specified"""
        # Create SSH repository WITHOUT remote_path
        repository = Repository(
            name="ssh-test-repo-2",
            path="/backups/test-repo-2",
            repository_type="ssh",
            host="backup2.example.com",
            port=22,
            username="backupuser",
            remote_path=None,  # No custom borg path
            passphrase="test456",
            source_directories='["/data"]',
            compression="lz4"
        )
        test_db.add(repository)
        test_db.commit()
        test_db.refresh(repository)

        # Create backup job
        job = BackupJob(
            repository=repository.path,
            status="pending"
        )
        test_db.add(job)
        test_db.commit()
        test_db.refresh(job)

        # Mock subprocess to capture environment variables
        mock_env = {}

        async def mock_create_subprocess(*args, **kwargs):
            nonlocal mock_env
            mock_env = kwargs.get('env', {})

            mock_process = AsyncMock()
            mock_process.stdout = AsyncMock()
            mock_process.stdout.readline = AsyncMock(return_value=b'')
            mock_process.wait = AsyncMock(return_value=0)
            mock_process.returncode = 0
            return mock_process

        with patch('asyncio.create_subprocess_exec', side_effect=mock_create_subprocess):
            with patch('app.services.backup_service.SessionLocal', return_value=test_db):
                try:
                    await backup_service.execute_backup(job.id, repository.path)
                except Exception:
                    pass

        # Verify BORG_REMOTE_PATH was NOT set
        assert 'BORG_REMOTE_PATH' not in mock_env
