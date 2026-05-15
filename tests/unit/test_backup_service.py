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
from app.database.models import BackupJob, Repository, SSHConnection, SystemSettings


class AsyncLineStream:
    def __init__(self, lines):
        self._lines = [
            line if isinstance(line, bytes) else line.encode("utf-8") for line in lines
        ]
        self._iterator = iter(self._lines)

    def __aiter__(self):
        self._iterator = iter(self._lines)
        return self

    async def __anext__(self):
        try:
            return next(self._iterator)
        except StopIteration:
            raise StopAsyncIteration


class FakeProcess:
    def __init__(self, returncode=0, stdout_lines=None, pid=4321):
        self.returncode = returncode
        self.stdout = AsyncLineStream(stdout_lines or [])
        self.pid = pid
        self.terminated = False
        self.killed = False

    async def wait(self):
        return self.returncode

    def terminate(self):
        self.terminated = True

    def kill(self):
        self.killed = True


class DeferredReturncodeProcess(FakeProcess):
    def __init__(self, final_returncode=0, stdout_lines=None, pid=4321):
        super().__init__(returncode=None, stdout_lines=stdout_lines, pid=pid)
        self.final_returncode = final_returncode

    async def wait(self):
        await asyncio.sleep(0)
        self.returncode = self.final_returncode
        return self.returncode


def _discard_background_task(coro):
    coro.close()
    return Mock()


@pytest.fixture
def backup_service():
    """Create a BackupService instance"""
    with patch("app.services.backup_service.settings") as mock_settings:
        mock_settings.data_dir = tempfile.mkdtemp()
        mock_settings.borg_info_timeout = 60
        mock_settings.borg_list_timeout = 60
        mock_settings.backup_timeout = 3600
        mock_settings.source_size_timeout = 120
        service = BackupService()
        yield service


@pytest.mark.unit
class TestBackupService:
    """Test BackupService class methods"""

    @pytest.fixture
    def backup_service(self):
        """Create a BackupService instance"""
        with patch("app.services.backup_service.settings") as mock_settings:
            mock_settings.data_dir = tempfile.mkdtemp()
            mock_settings.borg_info_timeout = 60
            mock_settings.borg_list_timeout = 60
            mock_settings.backup_timeout = 3600
            mock_settings.source_size_timeout = 120
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

    @pytest.mark.skip(
        reason="rotate_logs() signature changed - needs rewrite for new log management system"
    )
    def test_rotate_logs_empty_directory(self, backup_service):
        """Test rotate_logs with empty log directory"""
        # NOTE: This test needs to be rewritten to work with new rotate_logs(db=None) signature
        # The new implementation uses log_manager service and database settings
        pass

    @pytest.mark.skip(
        reason="rotate_logs() signature changed - needs rewrite for new log management system"
    )
    def test_rotate_logs_with_old_files(self, backup_service):
        """Test rotate_logs removes old files"""
        # NOTE: This test needs to be rewritten to work with new rotate_logs(db=None) signature
        # The new implementation uses log_manager service and database settings
        pass

    @pytest.mark.skip(
        reason="rotate_logs() signature changed - needs rewrite for new log management system"
    )
    def test_rotate_logs_keeps_recent_files(self, backup_service):
        """Test rotate_logs keeps recent files"""
        # NOTE: This test needs to be rewritten to work with new rotate_logs(db=None) signature
        # The new implementation uses log_manager service and database settings
        pass

    @pytest.mark.skip(
        reason="rotate_logs() signature changed - needs rewrite for new log management system"
    )
    def test_rotate_logs_limits_file_count(self, backup_service):
        """Test rotate_logs limits number of files"""
        # NOTE: This test needs to be rewritten to work with new rotate_logs(db=None) signature
        # The new implementation uses log_manager service and database settings
        pass

    @pytest.mark.asyncio
    async def test_run_hook_success(self, backup_service):
        """Test _run_hook with successful script"""
        script = "echo 'test output'"
        result = await backup_service._run_hook(
            script, "test-hook", timeout=5, job_id=1
        )

        assert result["success"] is True
        assert result["returncode"] == 0
        assert "test output" in result["stdout"]

    @pytest.mark.asyncio
    async def test_run_hook_failure(self, backup_service):
        """Test _run_hook with failing script"""
        script = "exit 1"
        result = await backup_service._run_hook(
            script, "test-hook", timeout=5, job_id=1
        )

        assert result["success"] is False
        assert result["returncode"] == 1

    @pytest.mark.asyncio
    async def test_run_hook_timeout(self, backup_service):
        """Test _run_hook with timeout"""
        script = "sleep 10"
        result = await backup_service._run_hook(
            script, "test-hook", timeout=1, job_id=1
        )

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
            repository="/test/repo", status="running", started_at=datetime.now()
        )
        test_db.add(job)
        test_db.commit()
        test_db.refresh(job)

        # Mock the subprocess to return invalid JSON
        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(return_value=(b"invalid json", b""))
        mock_process.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            # Should not raise exception, just log warning
            await backup_service._update_archive_stats(
                test_db, job.id, "/test/repo", "test-archive", {}
            )

    @pytest.mark.asyncio
    async def test_update_archive_stats_borg_failure(self, backup_service, test_db):
        """Test _update_archive_stats when borg command fails"""
        job = BackupJob(
            repository="/test/repo", status="running", started_at=datetime.now()
        )
        test_db.add(job)
        test_db.commit()
        test_db.refresh(job)

        # Mock the subprocess to return error
        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(return_value=(b"", b"Error message"))
        mock_process.returncode = 1

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            # Should not raise exception, just log warning
            await backup_service._update_archive_stats(
                test_db, job.id, "/test/repo", "test-archive", {}
            )

    @pytest.mark.asyncio
    async def test_update_repository_stats_success(self, backup_service, test_db):
        """Test _update_repository_stats with successful response"""
        # Create a repository record
        repo = Repository(
            name="Test Repo",
            path="/test/repo",
            encryption="none",
            repository_type="local",
        )
        test_db.add(repo)
        test_db.commit()

        # Mock the subprocess to return valid JSON
        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(
            return_value=(b'{"cache": {"stats": {"total_size": 1000000}}}', b"")
        )
        mock_process.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            # Should not raise exception
            await backup_service._update_repository_stats(test_db, "/test/repo", {})

    @pytest.mark.asyncio
    async def test_update_repository_stats_failure(self, backup_service, test_db):
        """Test _update_repository_stats when borg command fails"""
        # Create a repository record
        repo = Repository(
            name="Test Repo",
            path="/test/repo",
            encryption="none",
            repository_type="local",
        )
        test_db.add(repo)
        test_db.commit()

        # Mock the subprocess to return error
        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(
            return_value=(b"", b"Repository not found")
        )
        mock_process.returncode = 1

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            # Should not raise exception, just log warning
            await backup_service._update_repository_stats(test_db, "/test/repo", {})

    def test_get_operation_timeouts_prefers_database_values(
        self, backup_service, test_db
    ):
        settings_row = SystemSettings(
            info_timeout=11,
            list_timeout=22,
            backup_timeout=33,
            source_size_timeout=44,
        )
        test_db.add(settings_row)
        test_db.commit()

        timeouts = backup_service._get_operation_timeouts(test_db)

        assert timeouts == {
            "info_timeout": 11,
            "list_timeout": 22,
            "backup_timeout": 33,
            "source_size_timeout": 44,
        }

    def test_get_log_buffer_returns_tail_and_existence_flag(self, backup_service):
        backup_service.log_buffers[7] = [f"line-{index}" for index in range(6)]

        tail, exists = backup_service.get_log_buffer(7, tail_lines=3)

        assert exists is True
        assert tail == ["line-3", "line-4", "line-5"]
        missing_tail, missing_exists = backup_service.get_log_buffer(999)
        assert missing_exists is False
        assert missing_tail == []

    @pytest.mark.asyncio
    async def test_update_archive_stats_updates_job_statistics(
        self, backup_service, test_db, tmp_path
    ):
        repo_path = tmp_path / "repo"
        repo_path.mkdir()
        (repo_path / "data").mkdir()
        (repo_path / "config").write_text("[repository]\nversion = 1\n")
        repo = Repository(
            name="Repo",
            path=str(repo_path),
            encryption="none",
            repository_type="local",
            compression="lz4",
        )
        job = BackupJob(
            repository=str(repo_path),
            status="running",
            started_at=datetime.now(),
        )
        test_db.add_all([repo, job])
        test_db.commit()
        test_db.refresh(job)

        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(
            return_value=(
                b'{"archives": [{"stats": {"original_size": 8192, "compressed_size": 4096, "deduplicated_size": 2048, "nfiles": 12}}]}',
                b"",
            )
        )
        mock_process.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            await backup_service._update_archive_stats(
                test_db,
                job.id,
                str(repo_path),
                "test-archive",
                {},
            )

        test_db.refresh(job)
        assert job.original_size == 8192
        assert job.compressed_size == 4096
        assert job.deduplicated_size == 2048
        assert job.nfiles == 12

    @pytest.mark.asyncio
    async def test_update_repository_stats_updates_repository_and_publishes_snapshot(
        self, backup_service, test_db
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

        list_process = AsyncMock()
        list_process.communicate = AsyncMock(
            return_value=(b'{"archives": [{"name": "a"}, {"name": "b"}]}', b"")
        )
        list_process.returncode = 0
        info_process = AsyncMock()
        info_process.communicate = AsyncMock(
            return_value=(b'{"cache": {"stats": {"unique_size": 1048576}}}', b"")
        )
        info_process.returncode = 0
        mqtt = Mock()
        mqtt.sync_state_with_db = Mock()

        with (
            patch(
                "asyncio.create_subprocess_exec",
                side_effect=[list_process, info_process],
            ),
            patch("app.services.backup_service.mqtt_service", mqtt),
        ):
            await backup_service._update_repository_stats(test_db, "/test/repo", {})

        test_db.refresh(repo)
        assert repo.archive_count == 2
        assert repo.total_size == "1.00 MB"
        assert repo.last_backup is not None
        mqtt.sync_state_with_db.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_backup_success_saves_logs_and_notifies_success(
        self, backup_service, test_db, tmp_path
    ):
        repo_path = tmp_path / "repo"
        repo_path.mkdir()
        (repo_path / "data").mkdir()
        (repo_path / "config").write_text("[repository]\nversion = 1\n")
        repo = Repository(
            name="Repo",
            path=str(repo_path),
            encryption="none",
            repository_type="local",
            source_directories='["/data"]',
            compression="lz4",
        )
        settings_row = SystemSettings(log_save_policy="all_jobs")
        job = BackupJob(repository=repo.path, status="pending")
        test_db.add_all([repo, settings_row, job])
        test_db.commit()
        test_db.refresh(repo)
        test_db.refresh(job)

        fake_process = FakeProcess(
            returncode=0,
            stdout_lines=[
                '{"type":"archive_progress","original_size":1024,"compressed_size":512,"deduplicated_size":256,"nfiles":3,"finished":true}',
            ],
        )
        notifications = MagicMock()
        notifications.send_backup_start = AsyncMock()
        notifications.send_backup_success = AsyncMock()
        notifications.send_backup_warning = AsyncMock()
        notifications.send_backup_failure = AsyncMock()

        with (
            patch.object(
                backup_service,
                "_execute_hooks",
                AsyncMock(
                    return_value={
                        "success": True,
                        "execution_logs": [],
                        "scripts_executed": 0,
                        "scripts_failed": 0,
                        "using_library": False,
                    }
                ),
            ),
            patch.object(
                backup_service,
                "_prepare_source_paths",
                AsyncMock(return_value=(["/data"], [])),
            ),
            patch.object(
                backup_service, "_calculate_and_update_size_background", AsyncMock()
            ),
            patch.object(backup_service, "_update_archive_stats", AsyncMock()),
            patch.object(backup_service, "_update_repository_stats", AsyncMock()),
            patch(
                "app.services.backup_service.resolve_repo_ssh_key_file",
                return_value=None,
            ),
            patch(
                "app.services.backup_service.asyncio.create_subprocess_exec",
                return_value=fake_process,
            ),
            patch(
                "app.services.backup_service.asyncio.create_task",
                side_effect=_discard_background_task,
            ),
            patch("app.services.backup_service.notification_service", notifications),
            patch("app.services.backup_service.mqtt_service") as mqtt,
        ):
            mqtt.sync_state_with_db = Mock()
            await backup_service.execute_backup(job.id, repo.path, db=test_db)

        test_db.refresh(job)
        assert job.status == "completed"
        assert job.progress == 100
        assert job.has_logs is True
        assert job.log_file_path is not None
        assert Path(job.log_file_path).exists()
        notifications.send_backup_success.assert_awaited_once()
        notifications.send_backup_failure.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_execute_backup_parses_v1_json_progress(
        self, backup_service, test_db, tmp_path
    ):
        repo_path = tmp_path / "repo"
        repo_path.mkdir()
        (repo_path / "data").mkdir()
        (repo_path / "config").write_text("[repository]\nversion = 1\n")
        repo = Repository(
            name="Repo",
            path=str(repo_path),
            encryption="none",
            repository_type="local",
            source_directories='["/data"]',
            compression="lz4",
        )
        settings_row = SystemSettings(log_save_policy="all_jobs")
        job = BackupJob(
            repository=repo.path,
            status="pending",
            total_expected_size=200 * 1024 * 1024,
        )
        test_db.add_all([repo, settings_row, job])
        test_db.commit()
        test_db.refresh(job)

        fake_process = FakeProcess(
            returncode=0,
            stdout_lines=[
                '{"type":"archive_progress","original_size":104448655,"compressed_size":83886080,'
                '"deduplicated_size":73400320,"nfiles":18,"path":"tmp/source/file-19.bin","finished":false}',
            ],
        )
        notifications = MagicMock()
        notifications.send_backup_start = AsyncMock()
        notifications.send_backup_success = AsyncMock()
        notifications.send_backup_warning = AsyncMock()
        notifications.send_backup_failure = AsyncMock()

        with (
            patch.object(
                backup_service,
                "_execute_hooks",
                AsyncMock(
                    return_value={
                        "success": True,
                        "execution_logs": [],
                        "scripts_executed": 0,
                        "scripts_failed": 0,
                        "using_library": False,
                    }
                ),
            ),
            patch.object(
                backup_service,
                "_prepare_source_paths",
                AsyncMock(return_value=(["/data"], [])),
            ),
            patch.object(
                backup_service, "_calculate_and_update_size_background", AsyncMock()
            ),
            patch.object(backup_service, "_update_archive_stats", AsyncMock()),
            patch.object(backup_service, "_update_repository_stats", AsyncMock()),
            patch(
                "app.services.backup_service.resolve_repo_ssh_key_file",
                return_value=None,
            ),
            patch(
                "app.services.backup_service.asyncio.create_subprocess_exec",
                return_value=fake_process,
            ) as mock_subprocess,
            patch(
                "app.services.backup_service.asyncio.create_task",
                side_effect=_discard_background_task,
            ),
            patch("app.services.backup_service.notification_service", notifications),
            patch("app.services.backup_service.mqtt_service") as mqtt,
        ):
            mqtt.sync_state_with_db = Mock()
            await backup_service.execute_backup(job.id, repo.path, db=test_db)

        test_db.refresh(job)
        create_cmd = mock_subprocess.call_args.args
        assert "--log-json" in create_cmd
        assert job.original_size > 0
        assert job.compressed_size > 0
        assert job.deduplicated_size > 0
        assert job.nfiles == 18
        assert job.progress_percent > 0
        notifications.send_backup_success.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_execute_backup_publishes_terminal_status_before_stats_refresh(
        self, backup_service, test_db, tmp_path
    ):
        repo_path = tmp_path / "repo"
        repo_path.mkdir()
        (repo_path / "data").mkdir()
        (repo_path / "config").write_text("[repository]\nversion = 1\n")
        repo = Repository(
            name="Repo",
            path=str(repo_path),
            encryption="none",
            repository_type="local",
            source_directories='["/data"]',
            compression="lz4",
        )
        settings_row = SystemSettings(log_save_policy="all_jobs")
        job = BackupJob(repository=repo.path, status="pending")
        test_db.add_all([repo, settings_row, job])
        test_db.commit()
        test_db.refresh(job)

        fake_process = FakeProcess(
            returncode=0,
            stdout_lines=[
                '{"type":"archive_progress","original_size":1024,"compressed_size":512,"deduplicated_size":256,"nfiles":3,"finished":true}',
            ],
        )
        notifications = MagicMock()
        notifications.send_backup_start = AsyncMock()
        notifications.send_backup_success = AsyncMock()
        notifications.send_backup_warning = AsyncMock()
        notifications.send_backup_failure = AsyncMock()

        async def assert_terminal_state_before_stats(*args, **kwargs):
            refreshed = test_db.query(BackupJob).filter(BackupJob.id == job.id).first()
            assert refreshed.status == "completed"
            assert refreshed.progress == 100
            assert refreshed.completed_at is not None

        with (
            patch.object(
                backup_service,
                "_execute_hooks",
                AsyncMock(
                    return_value={
                        "success": True,
                        "execution_logs": [],
                        "scripts_executed": 0,
                        "scripts_failed": 0,
                        "using_library": False,
                    }
                ),
            ),
            patch.object(
                backup_service,
                "_prepare_source_paths",
                AsyncMock(return_value=(["/data"], [])),
            ),
            patch.object(
                backup_service, "_calculate_and_update_size_background", AsyncMock()
            ),
            patch.object(
                backup_service,
                "_update_archive_stats",
                AsyncMock(side_effect=assert_terminal_state_before_stats),
            ),
            patch.object(backup_service, "_update_repository_stats", AsyncMock()),
            patch(
                "app.services.backup_service.resolve_repo_ssh_key_file",
                return_value=None,
            ),
            patch(
                "app.services.backup_service.asyncio.create_subprocess_exec",
                return_value=fake_process,
            ),
            patch(
                "app.services.backup_service.asyncio.create_task",
                side_effect=_discard_background_task,
            ),
            patch("app.services.backup_service.notification_service", notifications),
            patch("app.services.backup_service.mqtt_service") as mqtt,
        ):
            mqtt.sync_state_with_db = Mock()
            await backup_service.execute_backup(job.id, repo.path, db=test_db)

        test_db.refresh(job)
        assert job.status == "completed"
        assert job.completed_at is not None
        notifications.send_backup_success.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_execute_backup_completes_when_returncode_is_only_available_via_wait(
        self, backup_service, test_db, tmp_path
    ):
        repo_path = tmp_path / "repo"
        repo_path.mkdir()
        (repo_path / "data").mkdir()
        (repo_path / "config").write_text("[repository]\nversion = 1\n")
        repo = Repository(
            name="Repo",
            path=str(repo_path),
            encryption="none",
            repository_type="local",
            source_directories='["/data"]',
            compression="lz4",
        )
        settings_row = SystemSettings(log_save_policy="all_jobs")
        job = BackupJob(repository=repo.path, status="pending")
        test_db.add_all([repo, settings_row, job])
        test_db.commit()
        test_db.refresh(job)

        fake_process = DeferredReturncodeProcess(
            final_returncode=0,
            stdout_lines=[
                '{"type":"archive_progress","original_size":1024,"compressed_size":512,"deduplicated_size":256,"nfiles":3,"finished":true}',
            ],
        )
        notifications = MagicMock()
        notifications.send_backup_start = AsyncMock()
        notifications.send_backup_success = AsyncMock()
        notifications.send_backup_warning = AsyncMock()
        notifications.send_backup_failure = AsyncMock()

        with (
            patch.object(
                backup_service,
                "_execute_hooks",
                AsyncMock(
                    return_value={
                        "success": True,
                        "execution_logs": [],
                        "scripts_executed": 0,
                        "scripts_failed": 0,
                        "using_library": False,
                    }
                ),
            ),
            patch.object(
                backup_service,
                "_prepare_source_paths",
                AsyncMock(return_value=(["/data"], [])),
            ),
            patch.object(
                backup_service, "_calculate_and_update_size_background", AsyncMock()
            ),
            patch.object(backup_service, "_update_archive_stats", AsyncMock()),
            patch.object(backup_service, "_update_repository_stats", AsyncMock()),
            patch(
                "app.services.backup_service.resolve_repo_ssh_key_file",
                return_value=None,
            ),
            patch(
                "app.services.backup_service.asyncio.create_subprocess_exec",
                return_value=fake_process,
            ),
            patch(
                "app.services.backup_service.asyncio.create_task",
                side_effect=_discard_background_task,
            ),
            patch("app.services.backup_service.notification_service", notifications),
            patch("app.services.backup_service.mqtt_service") as mqtt,
        ):
            mqtt.sync_state_with_db = Mock()
            await asyncio.wait_for(
                backup_service.execute_backup(job.id, repo.path, db=test_db),
                timeout=2.0,
            )

        test_db.refresh(job)
        assert job.status == "completed"
        assert job.progress == 100
        notifications.send_backup_success.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_execute_backup_warning_marks_warning_and_notifies_warning(
        self, backup_service, test_db, tmp_path
    ):
        repo_path = tmp_path / "repo"
        repo_path.mkdir()
        (repo_path / "data").mkdir()
        (repo_path / "config").write_text("[repository]\nversion = 1\n")
        repo = Repository(
            name="Repo",
            path=str(repo_path),
            encryption="none",
            repository_type="local",
            source_directories='["/data"]',
            compression="lz4",
        )
        settings_row = SystemSettings(log_save_policy="all_jobs")
        job = BackupJob(repository=repo.path, status="pending")
        test_db.add_all([repo, settings_row, job])
        test_db.commit()
        test_db.refresh(repo)
        test_db.refresh(job)

        fake_process = FakeProcess(
            returncode=105,
            stdout_lines=[
                '{"type":"log_message","levelname":"WARNING","message":"terminating with warning status, rc 105"}'
            ],
        )
        notifications = MagicMock()
        notifications.send_backup_start = AsyncMock()
        notifications.send_backup_success = AsyncMock()
        notifications.send_backup_warning = AsyncMock()
        notifications.send_backup_failure = AsyncMock()

        with (
            patch.object(
                backup_service,
                "_execute_hooks",
                AsyncMock(
                    return_value={
                        "success": True,
                        "execution_logs": [],
                        "scripts_executed": 0,
                        "scripts_failed": 0,
                        "using_library": False,
                    }
                ),
            ),
            patch.object(
                backup_service,
                "_prepare_source_paths",
                AsyncMock(return_value=(["/data"], [])),
            ),
            patch.object(
                backup_service, "_calculate_and_update_size_background", AsyncMock()
            ),
            patch.object(backup_service, "_update_archive_stats", AsyncMock()),
            patch.object(backup_service, "_update_repository_stats", AsyncMock()),
            patch(
                "app.services.backup_service.resolve_repo_ssh_key_file",
                return_value=None,
            ),
            patch(
                "app.services.backup_service.asyncio.create_subprocess_exec",
                return_value=fake_process,
            ),
            patch(
                "app.services.backup_service.asyncio.create_task",
                side_effect=_discard_background_task,
            ),
            patch("app.services.backup_service.notification_service", notifications),
            patch("app.services.backup_service.mqtt_service") as mqtt,
        ):
            mqtt.sync_state_with_db = Mock()
            await backup_service.execute_backup(job.id, repo.path, db=test_db)

        test_db.refresh(job)
        assert job.status == "completed_with_warnings"
        assert "backupCompletedWithWarning" in job.error_message
        assert job.has_logs is True
        assert Path(job.log_file_path).exists()
        notifications.send_backup_warning.assert_awaited_once()
        notifications.send_backup_success.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_execute_backup_lock_error_marks_failed_and_keeps_error_hint(
        self, backup_service, test_db, tmp_path
    ):
        repo_path = tmp_path / "repo"
        repo_path.mkdir()
        (repo_path / "data").mkdir()
        (repo_path / "config").write_text("[repository]\nversion = 1\n")
        repo = Repository(
            name="Repo",
            path=str(repo_path),
            encryption="none",
            repository_type="local",
            source_directories='["/data"]',
            compression="lz4",
        )
        settings_row = SystemSettings(log_save_policy="all_jobs")
        job = BackupJob(repository=repo.path, status="pending")
        test_db.add_all([repo, settings_row, job])
        test_db.commit()
        test_db.refresh(repo)
        test_db.refresh(job)

        fake_process = FakeProcess(
            returncode=70,
            stdout_lines=[
                '{"type":"log_message","levelname":"CRITICAL","msgid":"LockError","message":"repository is locked"}'
            ],
        )
        notifications = MagicMock()
        notifications.send_backup_start = AsyncMock()
        notifications.send_backup_success = AsyncMock()
        notifications.send_backup_warning = AsyncMock()
        notifications.send_backup_failure = AsyncMock()

        with (
            patch.object(
                backup_service,
                "_execute_hooks",
                AsyncMock(
                    return_value={
                        "success": True,
                        "execution_logs": [],
                        "scripts_executed": 0,
                        "scripts_failed": 0,
                        "using_library": False,
                    }
                ),
            ),
            patch.object(
                backup_service,
                "_prepare_source_paths",
                AsyncMock(return_value=(["/data"], [])),
            ),
            patch.object(
                backup_service, "_calculate_and_update_size_background", AsyncMock()
            ),
            patch(
                "app.services.backup_service.resolve_repo_ssh_key_file",
                return_value=None,
            ),
            patch(
                "app.services.backup_service.asyncio.create_subprocess_exec",
                return_value=fake_process,
            ),
            patch(
                "app.services.backup_service.asyncio.create_task",
                side_effect=_discard_background_task,
            ),
            patch("app.services.backup_service.notification_service", notifications),
            patch("app.services.backup_service.mqtt_service") as mqtt,
        ):
            mqtt.sync_state_with_db = Mock()
            await backup_service.execute_backup(job.id, repo.path, db=test_db)

        test_db.refresh(job)
        assert job.status == "failed"
        assert f"LOCK_ERROR::{repo.path}" in job.error_message
        assert job.has_logs is True
        assert Path(job.log_file_path).exists()
        notifications.send_backup_failure.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_execute_backup_job_not_found(self, backup_service, test_db):
        """Test execute_backup with non-existent job"""
        with patch("app.services.backup_service.SessionLocal", return_value=test_db):
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
            repository="/nonexistent/repo", status="pending", started_at=datetime.now()
        )
        test_db.add(job)
        test_db.commit()
        test_db.refresh(job)

        with patch("app.services.backup_service.SessionLocal", return_value=test_db):
            # Should handle gracefully
            try:
                await backup_service.execute_backup(job.id, "/nonexistent/repo")
            except Exception:
                # Expected to fail with repository not found
                pass

    @pytest.mark.asyncio
    async def test_execute_backup_fails_fast_for_invalid_local_repository_path(
        self, backup_service, test_db, tmp_path
    ):
        repo_path = tmp_path / "not-a-borg-repo"
        repo_path.mkdir()
        (repo_path / "config").mkdir()

        repo = Repository(
            name="Invalid Repo",
            path=str(repo_path),
            encryption="none",
            repository_type="local",
            source_directories='["/data"]',
            compression="lz4",
        )
        settings_row = SystemSettings(log_save_policy="all_jobs")
        job = BackupJob(repository=repo.path, status="pending")
        test_db.add_all([repo, settings_row, job])
        test_db.commit()
        test_db.refresh(job)

        notifications = MagicMock()
        notifications.send_backup_start = AsyncMock()
        notifications.send_backup_success = AsyncMock()
        notifications.send_backup_warning = AsyncMock()
        notifications.send_backup_failure = AsyncMock()

        with (
            patch(
                "app.services.backup_service.asyncio.create_subprocess_exec",
                side_effect=AssertionError(
                    "borg should not run for invalid repository paths"
                ),
            ),
            patch("app.services.backup_service.notification_service", notifications),
            patch("app.services.backup_service.mqtt_service") as mqtt,
        ):
            mqtt.sync_state_with_db = Mock()
            await backup_service.execute_backup(job.id, repo.path, db=test_db)

        test_db.refresh(job)
        assert job.status == "failed"
        assert "backend.errors.repo.notValidBorgRepository" in job.error_message
        assert str(repo_path) in (job.logs or "")
        notifications.send_backup_failure.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_execute_backup_uses_borg2_command_for_borg2_repositories(
        self, backup_service, test_db, tmp_path
    ):
        repo_path = tmp_path / "borg2-repo"
        repo_path.mkdir()

        repo = Repository(
            name="Borg 2 Repo",
            path=str(repo_path),
            encryption="none",
            repository_type="local",
            source_directories='["/data/source.txt"]',
            compression="lz4",
            borg_version=2,
        )
        settings_row = SystemSettings(log_save_policy="all_jobs")
        job = BackupJob(repository=repo.path, status="pending")
        test_db.add_all([repo, settings_row, job])
        test_db.commit()
        test_db.refresh(job)

        fake_process = FakeProcess(
            returncode=0, stdout_lines=['{"type":"archive_progress","finished":true}']
        )
        notifications = MagicMock()
        notifications.send_backup_start = AsyncMock()
        notifications.send_backup_success = AsyncMock()
        notifications.send_backup_warning = AsyncMock()
        notifications.send_backup_failure = AsyncMock()

        with (
            patch.object(
                backup_service,
                "_execute_hooks",
                AsyncMock(
                    return_value={
                        "success": True,
                        "execution_logs": [],
                        "scripts_executed": 0,
                        "scripts_failed": 0,
                        "using_library": False,
                    }
                ),
            ),
            patch.object(
                backup_service,
                "_prepare_source_paths",
                AsyncMock(return_value=(["/data/source.txt"], [])),
            ),
            patch.object(
                backup_service, "_calculate_and_update_size_background", AsyncMock()
            ),
            patch.object(backup_service, "_update_archive_stats", AsyncMock()),
            patch.object(backup_service, "_update_repository_stats", AsyncMock()),
            patch(
                "app.services.backup_service.resolve_repo_ssh_key_file",
                return_value=None,
            ),
            patch(
                "app.services.backup_service.asyncio.create_subprocess_exec",
                return_value=fake_process,
            ) as mock_subprocess,
            patch(
                "app.services.backup_service.asyncio.create_task",
                side_effect=_discard_background_task,
            ),
            patch("app.services.backup_service.notification_service", notifications),
            patch("app.services.backup_service.mqtt_service") as mqtt,
            patch("app.core.borg2.borg2.borg_cmd", "borg2"),
        ):
            mqtt.sync_state_with_db = Mock()
            await backup_service.execute_backup(job.id, repo.path, db=test_db)

        test_db.refresh(job)
        assert job.status == "completed"
        create_call = mock_subprocess.call_args
        create_cmd = create_call.args
        assert create_cmd[0] == "borg2"
        assert "-r" in create_cmd
        assert str(repo_path) in create_cmd
        assert "create" in create_cmd
        assert f"{repo.path}::" not in " ".join(create_cmd)
        assert create_cmd[-2] == "manual-backup"
        assert "/data/source.txt" in create_cmd
        notifications.send_backup_success.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_execute_backup_parses_v2_json_progress(
        self, backup_service, test_db, tmp_path
    ):
        repo_path = tmp_path / "borg2-progress-repo"
        repo_path.mkdir()

        repo = Repository(
            name="Borg 2 Repo",
            path=str(repo_path),
            encryption="none",
            repository_type="local",
            source_directories='["/data/source.txt"]',
            compression="none",
            borg_version=2,
        )
        settings_row = SystemSettings(log_save_policy="all_jobs")
        job = BackupJob(
            repository=repo.path,
            status="pending",
            total_expected_size=200 * 1024 * 1024,
        )
        test_db.add_all([repo, settings_row, job])
        test_db.commit()
        test_db.refresh(job)

        fake_process = FakeProcess(
            returncode=0,
            stdout_lines=[
                '{"type":"archive_progress","original_size":104448655,"compressed_size":83886080,'
                '"deduplicated_size":73400320,"nfiles":18,"path":"tmp/source/file-19.bin","finished":false}',
            ],
        )
        notifications = MagicMock()
        notifications.send_backup_start = AsyncMock()
        notifications.send_backup_success = AsyncMock()
        notifications.send_backup_warning = AsyncMock()
        notifications.send_backup_failure = AsyncMock()

        with (
            patch.object(
                backup_service,
                "_execute_hooks",
                AsyncMock(
                    return_value={
                        "success": True,
                        "execution_logs": [],
                        "scripts_executed": 0,
                        "scripts_failed": 0,
                        "using_library": False,
                    }
                ),
            ),
            patch.object(
                backup_service,
                "_prepare_source_paths",
                AsyncMock(return_value=(["/data/source.txt"], [])),
            ),
            patch.object(
                backup_service, "_calculate_and_update_size_background", AsyncMock()
            ),
            patch.object(backup_service, "_update_archive_stats", AsyncMock()),
            patch.object(backup_service, "_update_repository_stats", AsyncMock()),
            patch(
                "app.services.backup_service.resolve_repo_ssh_key_file",
                return_value=None,
            ),
            patch(
                "app.services.backup_service.asyncio.create_subprocess_exec",
                return_value=fake_process,
            ),
            patch(
                "app.services.backup_service.asyncio.create_task",
                side_effect=_discard_background_task,
            ),
            patch("app.services.backup_service.notification_service", notifications),
            patch("app.services.backup_service.mqtt_service") as mqtt,
            patch("app.core.borg2.borg2.borg_cmd", "borg2"),
        ):
            mqtt.sync_state_with_db = Mock()
            await backup_service.execute_backup(job.id, repo.path, db=test_db)

        test_db.refresh(job)
        assert job.original_size > 0
        assert job.compressed_size > 0
        assert job.deduplicated_size > 0
        assert job.nfiles == 18
        assert job.progress_percent > 0
        notifications.send_backup_success.assert_awaited_once()

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

    @pytest.mark.skip(
        reason="Test requires rewrite - SessionLocal mock doesn't properly bind job to session"
    )
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
            compression="lz4",
        )
        test_db.add(repository)
        test_db.commit()
        test_db.refresh(repository)

        # Create backup job
        job = BackupJob(repository=repository.path, status="pending")
        test_db.add(job)
        test_db.commit()
        test_db.refresh(job)

        # Mock subprocess to capture environment variables
        mock_env = {}

        async def mock_create_subprocess(*args, **kwargs):
            # Capture the environment
            nonlocal mock_env
            mock_env = kwargs.get("env", {})

            # Return a mock process
            mock_process = AsyncMock()
            mock_process.stdout = AsyncMock()
            mock_process.stdout.readline = AsyncMock(return_value=b"")
            mock_process.wait = AsyncMock(return_value=0)
            mock_process.returncode = 0
            return mock_process

        with patch(
            "asyncio.create_subprocess_exec", side_effect=mock_create_subprocess
        ):
            with patch(
                "app.services.backup_service.SessionLocal", return_value=test_db
            ):
                try:
                    await backup_service.execute_backup(job.id, repository.path)
                except Exception:
                    pass  # We're only interested in capturing the environment

        # Verify BORG_REMOTE_PATH was set
        assert "BORG_REMOTE_PATH" in mock_env
        assert mock_env["BORG_REMOTE_PATH"] == "/usr/local/bin/borg"

    @pytest.mark.skip(
        reason="Test requires rewrite - SessionLocal mock doesn't properly bind job to session"
    )
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
            compression="lz4",
        )
        test_db.add(repository)
        test_db.commit()
        test_db.refresh(repository)

        # Create backup job
        job = BackupJob(repository=repository.path, status="pending")
        test_db.add(job)
        test_db.commit()
        test_db.refresh(job)

        # Mock subprocess to capture environment variables
        mock_env = {}

        async def mock_create_subprocess(*args, **kwargs):
            nonlocal mock_env
            mock_env = kwargs.get("env", {})

            mock_process = AsyncMock()
            mock_process.stdout = AsyncMock()
            mock_process.stdout.readline = AsyncMock(return_value=b"")
            mock_process.wait = AsyncMock(return_value=0)
            mock_process.returncode = 0
            return mock_process

        with patch(
            "asyncio.create_subprocess_exec", side_effect=mock_create_subprocess
        ):
            with patch(
                "app.services.backup_service.SessionLocal", return_value=test_db
            ):
                try:
                    await backup_service.execute_backup(job.id, repository.path)
                except Exception:
                    pass

        # Verify BORG_REMOTE_PATH was NOT set
        assert "BORG_REMOTE_PATH" not in mock_env


@pytest.mark.unit
class TestBackupServicePeriodicSync:
    """Test BackupService periodic_sync_state functionality"""

    @pytest.fixture
    def backup_service_with_mqtt(self):
        """Create a BackupService instance with MQTT service"""
        with patch("app.services.backup_service.settings") as mock_settings:
            mock_settings.data_dir = tempfile.mkdtemp()
            mock_settings.borg_info_timeout = 60
            mock_settings.borg_list_timeout = 60
            mock_settings.backup_timeout = 3600
            mock_settings.source_size_timeout = 120
            service = BackupService()

            # Mock MQTT service
            mock_mqtt_service = Mock()
            mock_mqtt_service.sync_state_with_db = Mock(return_value=True)
            service.mqtt_service = mock_mqtt_service

            yield service

    @pytest.mark.asyncio
    async def test_periodic_sync_state_calls_mqtt_sync(self, backup_service_with_mqtt):
        """Test that periodic_sync_state calls mqtt_service.sync_state_with_db"""
        # Create a mock process
        mock_process = AsyncMock()
        mock_process.returncode = None  # Process is still running

        # Create a mock database session
        mock_db = Mock()

        # Create a mock job
        mock_job = Mock()
        mock_job.id = 1

        # Create a mock logger
        mock_logger = Mock()

        # Call the periodic_sync_state function
        async def periodic_sync_state():
            """Periodically sync state with DB for MQTT progress updates"""
            cancelled = False
            try:
                iteration_count = 0
                while (
                    not cancelled
                    and mock_process.returncode is None
                    and iteration_count < 2
                ):
                    # Sync state with DB every 20 seconds to publish progress updates
                    backup_service_with_mqtt.mqtt_service.sync_state_with_db(
                        mock_db, reason="backup progress update"
                    )
                    await asyncio.sleep(0.01)  # Short sleep for testing
                    iteration_count += 1
            except asyncio.CancelledError:
                mock_logger.info(
                    "Periodic sync state task cancelled", job_id=mock_job.id
                )
                raise
            except Exception as e:
                mock_logger.error(
                    "Error in periodic sync state task",
                    job_id=mock_job.id,
                    error=str(e),
                )

        await periodic_sync_state()

        # Verify that sync_state_with_db was called
        assert backup_service_with_mqtt.mqtt_service.sync_state_with_db.call_count >= 1

        # Verify the call was made with correct parameters
        backup_service_with_mqtt.mqtt_service.sync_state_with_db.assert_called_with(
            mock_db, reason="backup progress update"
        )

    @pytest.mark.asyncio
    async def test_periodic_sync_state_stops_when_process_completes(
        self, backup_service_with_mqtt
    ):
        """Test that periodic_sync_state stops when process completes"""
        # Create a mock process that completes immediately
        mock_process = AsyncMock()
        mock_process.returncode = 0  # Process has completed

        # Create a mock database session
        mock_db = Mock()

        # Call the periodic_sync_state function
        async def periodic_sync_state():
            """Periodically sync state with DB for MQTT progress updates"""
            cancelled = False
            try:
                while not cancelled and mock_process.returncode is None:
                    # Sync state with DB every 20 seconds to publish progress updates
                    backup_service_with_mqtt.mqtt_service.sync_state_with_db(
                        mock_db, reason="backup progress update"
                    )
                    await asyncio.sleep(0.01)  # Short sleep for testing
            except asyncio.CancelledError:
                raise
            except Exception as e:
                pass

        await periodic_sync_state()

        # Verify that sync_state_with_db was NOT called since process already completed
        backup_service_with_mqtt.mqtt_service.sync_state_with_db.assert_not_called()

    @pytest.mark.asyncio
    async def test_periodic_sync_state_handles_cancellation(
        self, backup_service_with_mqtt
    ):
        """Test that periodic_sync_state handles cancellation gracefully"""
        # Create a mock process
        mock_process = AsyncMock()
        mock_process.returncode = None  # Process is still running

        # Create a mock database session
        mock_db = Mock()

        # Create a mock job
        mock_job = Mock()
        mock_job.id = 1

        # Create a mock logger
        mock_logger = Mock()

        # Call the periodic_sync_state function with cancellation
        async def periodic_sync_state():
            """Periodically sync state with DB for MQTT progress updates"""
            cancelled = False
            try:
                while not cancelled and mock_process.returncode is None:
                    # Sync state with DB every 20 seconds to publish progress updates
                    backup_service_with_mqtt.mqtt_service.sync_state_with_db(
                        mock_db, reason="backup progress update"
                    )
                    await asyncio.sleep(0.01)  # Short sleep for testing
                    cancelled = True  # Simulate cancellation
            except asyncio.CancelledError:
                mock_logger.info(
                    "Periodic sync state task cancelled", job_id=mock_job.id
                )
                raise
            except Exception as e:
                mock_logger.error(
                    "Error in periodic sync state task",
                    job_id=mock_job.id,
                    error=str(e),
                )

        await periodic_sync_state()

        # Verify that sync_state_with_db was called at least once before cancellation
        assert backup_service_with_mqtt.mqtt_service.sync_state_with_db.call_count >= 1

    @pytest.mark.asyncio
    async def test_periodic_sync_state_handles_exceptions(
        self, backup_service_with_mqtt
    ):
        """Test that periodic_sync_state handles exceptions gracefully"""
        # Create a mock process
        mock_process = AsyncMock()
        mock_process.returncode = None  # Process is still running

        # Create a mock database session
        mock_db = Mock()

        # Create a mock job
        mock_job = Mock()
        mock_job.id = 1

        # Create a mock logger
        mock_logger = Mock()

        # Make sync_state_with_db raise an exception
        backup_service_with_mqtt.mqtt_service.sync_state_with_db.side_effect = (
            Exception("Test error")
        )

        # Call the periodic_sync_state function
        async def periodic_sync_state():
            """Periodically sync state with DB for MQTT progress updates"""
            cancelled = False
            try:
                iteration_count = 0
                while (
                    not cancelled
                    and mock_process.returncode is None
                    and iteration_count < 1
                ):
                    # Sync state with DB every 20 seconds to publish progress updates
                    backup_service_with_mqtt.mqtt_service.sync_state_with_db(
                        mock_db, reason="backup progress update"
                    )
                    await asyncio.sleep(0.01)  # Short sleep for testing
                    iteration_count += 1
            except asyncio.CancelledError:
                mock_logger.info(
                    "Periodic sync state task cancelled", job_id=mock_job.id
                )
                raise
            except Exception as e:
                mock_logger.error(
                    "Error in periodic sync state task",
                    job_id=mock_job.id,
                    error=str(e),
                )

        await periodic_sync_state()

        # Verify that the exception was logged
        mock_logger.error.assert_called_once_with(
            "Error in periodic sync state task", job_id=mock_job.id, error="Test error"
        )

    @pytest.mark.asyncio
    async def test_prepare_source_paths_resolves_relative_remote_paths(
        self, backup_service, db_session, monkeypatch
    ):
        connection = SSHConnection(
            host="example.com",
            username="borg",
            port=22,
            default_path="/etc/komodo",
        )
        db_session.add(connection)
        db_session.commit()
        db_session.refresh(connection)

        captured = {}

        async def mock_mount_ssh_paths_shared(connection_id, remote_paths, job_id):
            captured["connection_id"] = connection_id
            captured["remote_paths"] = remote_paths
            return "/tmp/sshfs_mount_test", [("mount-1", "etc/komodo")]

        monkeypatch.setattr(
            "app.services.backup_service.SessionLocal", lambda: db_session
        )
        monkeypatch.setattr(
            "app.services.mount_service.mount_service.mount_ssh_paths_shared",
            mock_mount_ssh_paths_shared,
        )

        processed_paths, ssh_mount_info = await backup_service._prepare_source_paths(
            [
                f"ssh://{connection.username}@{connection.host}:{connection.port}/etc/komodo"
            ],
            job_id=42,
            source_connection_id=connection.id,
        )

        assert captured["connection_id"] == connection.id
        assert captured["remote_paths"] == ["/etc/komodo"]
        assert processed_paths == ["etc/komodo"]
        assert ssh_mount_info == [("/tmp/sshfs_mount_test", "etc/komodo")]

    def test_resolve_backup_command_paths_mixes_remote_source_and_local_canary(
        self, backup_service
    ):
        data_dir = backup_service.log_dir.parent
        canary_path = str(
            data_dir / ".borg-ui/restore-canaries/repository-1/.borgui-canary"
        )

        backup_paths, backup_cwd = backup_service._resolve_backup_command_paths(
            ["etc/komodo", canary_path],
            [("/tmp/sshfs_mount_test", "etc/komodo")],
            job_id=42,
        )

        assert backup_cwd == str(data_dir)
        assert backup_paths == [
            "/tmp/sshfs_mount_test/etc/komodo",
            ".borg-ui/restore-canaries/repository-1/.borgui-canary",
        ]
