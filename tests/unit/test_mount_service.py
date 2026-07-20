"""
Unit tests for MountService
"""

import pytest
import tempfile
import os
from unittest.mock import Mock, patch, AsyncMock
from datetime import datetime, timezone

from app.services.mount_service import MountService, MountType, MountInfo
from app.database.models import SSHConnection, SSHKey, Repository


@pytest.mark.unit
class TestMountService:
    """Test MountService class methods"""

    @pytest.fixture
    def mount_service(self):
        """Create a MountService instance"""
        with patch("app.services.mount_service.settings") as mock_settings:
            mock_settings.data_dir = tempfile.mkdtemp()
            mock_settings.secret_key = "test_secret_key_32_characters!"
            service = MountService()
            yield service

    def test_init(self, mount_service):
        """Test MountService initialization"""
        assert mount_service is not None
        assert mount_service.active_mounts == {}
        assert mount_service.mount_base_dir.exists()

    def test_sshfs_symlink_options_preserve_is_faithful(self):
        """Backup sources disable the contain_symlinks sandbox and do not follow."""
        from app.services.mount_service import _sshfs_symlink_options

        opts = _sshfs_symlink_options(True)
        assert "no_contain_symlinks" in opts
        assert "follow_symlinks" not in opts

    def test_sshfs_symlink_options_default_follows(self):
        """Browse/restore/cloud-mirror keep the historical follow_symlinks."""
        from app.services.mount_service import _sshfs_symlink_options

        opts = _sshfs_symlink_options(False)
        assert "follow_symlinks" in opts
        assert "no_contain_symlinks" not in opts

    async def _capture_sshfs_argv(self, mount_service, *, preserve_symlinks):
        """Run _execute_sshfs_mount with a stubbed subprocess and return its argv."""
        from types import SimpleNamespace

        connection = SimpleNamespace(
            username="u", host="h", port=22, use_sudo=False, default_path=None
        )
        captured = {}
        proc = Mock()
        proc.returncode = 0
        proc.communicate = AsyncMock(return_value=(b"", b""))

        async def fake_exec(*args, **kwargs):
            captured["argv"] = list(args)
            return proc

        with (
            patch(
                "app.services.mount_service.asyncio.create_subprocess_exec",
                new=fake_exec,
            ),
            patch("app.services.mount_service.asyncio.sleep", new=AsyncMock()),
        ):
            await mount_service._execute_sshfs_mount(
                connection=connection,
                remote_path="/srv/data",
                mount_point="/mnt/x",
                temp_key_file="/tmp/key",
                preserve_symlinks=preserve_symlinks,
            )
        return captured["argv"]

    @pytest.mark.asyncio
    async def test_execute_sshfs_mount_backup_source_preserves_symlinks(
        self, mount_service
    ):
        argv = await self._capture_sshfs_argv(mount_service, preserve_symlinks=True)
        assert "no_contain_symlinks" in argv
        assert "follow_symlinks" not in argv

    @pytest.mark.asyncio
    async def test_execute_sshfs_mount_default_follows_symlinks(self, mount_service):
        argv = await self._capture_sshfs_argv(mount_service, preserve_symlinks=False)
        assert "follow_symlinks" in argv
        assert "no_contain_symlinks" not in argv

    def test_validate_mount_point_sensitive_paths(self, mount_service):
        """Test mount point validation rejects sensitive system paths"""
        sensitive_paths = [
            "/etc",
            "/root",
            "/sys",
            "/proc",
            "/boot",
            "/dev",
            "/var",
            "/usr",
        ]

        for path in sensitive_paths:
            with pytest.raises(Exception, match="Cannot mount to sensitive path"):
                mount_service._validate_mount_point(path)

            # Also test subpaths
            with pytest.raises(Exception, match="Cannot mount to sensitive path"):
                mount_service._validate_mount_point(f"{path}/subdir")

    def test_validate_mount_point_path_traversal(self, mount_service):
        """Test mount point validation rejects path traversal"""
        with pytest.raises(Exception, match="Path traversal not allowed"):
            mount_service._validate_mount_point("/tmp/../etc")

        with pytest.raises(Exception, match="Path traversal not allowed"):
            mount_service._validate_mount_point("/tmp/test/../../../etc")

    def test_validate_mount_point_relative_path(self, mount_service):
        """Test mount point validation requires absolute path"""
        with pytest.raises(Exception, match="must be an absolute path"):
            mount_service._validate_mount_point("relative/path")

    def test_validate_mount_point_valid(self, mount_service):
        """Test mount point validation accepts valid paths"""
        valid_paths = ["/tmp/mount", "/home/user/mount", "/mnt/data"]

        for path in valid_paths:
            # Should not raise exception
            mount_service._validate_mount_point(path)

    @pytest.mark.asyncio
    async def test_check_sshfs_available_found(self, mount_service):
        """Test SSHFS availability check when installed"""
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_process = AsyncMock()
            mock_process.communicate = AsyncMock(return_value=(b"", b""))
            mock_process.returncode = 0
            mock_exec.return_value = mock_process

            result = await mount_service._check_sshfs_available()
            assert result is True

    @pytest.mark.asyncio
    async def test_check_sshfs_available_not_found(self, mount_service):
        """Test SSHFS availability check when not installed"""
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_process = AsyncMock()
            mock_process.communicate = AsyncMock(return_value=(b"", b""))
            mock_process.returncode = 1
            mock_exec.return_value = mock_process

            result = await mount_service._check_sshfs_available()
            assert result is False

    def test_decrypt_and_write_key(self, mount_service):
        """Test SSH key decryption and temp file creation"""
        # Mock SSHKey with test data
        mock_ssh_key = Mock(spec=SSHKey)
        test_private_key = "-----BEGIN OPENSSH PRIVATE KEY-----\ntest_key_content\n-----END OPENSSH PRIVATE KEY-----\n"

        # Use a simpler approach: just test that the method creates a file with correct permissions
        # We'll mock the Fernet decryption itself
        with patch("app.services.mount_service.Fernet") as mock_fernet_class:
            mock_cipher = Mock()
            mock_cipher.decrypt.return_value = test_private_key.encode()
            mock_fernet_class.return_value = mock_cipher

            mock_ssh_key.private_key = "mock_encrypted_key"

            with patch("app.services.mount_service.settings") as mock_settings:
                mock_settings.secret_key = "test_secret_key_32_chars!!!!!"

                # Test key file creation
                temp_key_file = mount_service._decrypt_and_write_key(mock_ssh_key)

                try:
                    # Verify file exists
                    assert os.path.exists(temp_key_file)

                    # Verify permissions are 0o600
                    stat_info = os.stat(temp_key_file)
                    assert oct(stat_info.st_mode)[-3:] == "600"

                    # Verify content (with trailing newline added by the method)
                    with open(temp_key_file, "r") as f:
                        content = f.read()
                        assert content == test_private_key

                finally:
                    # Cleanup
                    if os.path.exists(temp_key_file):
                        os.unlink(temp_key_file)

    def test_cleanup_temp_files(self, mount_service):
        """Test temp file cleanup"""
        # Create temp directory and key file
        temp_root = tempfile.mkdtemp(prefix="test_mount_")
        temp_key_file = tempfile.NamedTemporaryFile(delete=False, suffix=".key").name

        # Verify they exist
        assert os.path.exists(temp_root)
        assert os.path.exists(temp_key_file)

        # Cleanup
        mount_service._cleanup_temp_files(temp_root, temp_key_file)

        # Verify they're gone
        assert not os.path.exists(temp_root)
        assert not os.path.exists(temp_key_file)

    def test_cleanup_orphaned_temp_dirs_removes_stable_sshfs_cache_roots(
        self, mount_service
    ):
        data_dir = mount_service.mount_base_dir.parent
        orphaned_root = data_dir / "sshfs-cache" / "repository-7"
        tracked_root = data_dir / "sshfs-cache" / "repository-8"
        orphaned_root.mkdir(parents=True)
        tracked_root.mkdir(parents=True)
        mount_service.active_mounts["tracked"] = MountInfo(
            mount_id="tracked",
            mount_type=MountType.SSHFS,
            mount_point=str(tracked_root / "srv"),
            source="sshfs://example/srv",
            created_at=datetime.now(timezone.utc),
            temp_root=str(tracked_root),
        )

        def glob_side_effect(pattern):
            if pattern == "/tmp/sshfs_mount_*":
                return []
            return [str(orphaned_root), str(tracked_root)]

        with patch("glob.glob", side_effect=glob_side_effect):
            mount_service._cleanup_orphaned_temp_dirs()

        assert not orphaned_root.exists()
        assert tracked_root.exists()

    def test_cleanup_orphaned_temp_dirs_preserves_mounted_stable_sshfs_cache_root(
        self, mount_service
    ):
        data_dir = mount_service.mount_base_dir.parent
        mounted_root = data_dir / "sshfs-cache" / "repository-9"
        mounted_path = mounted_root / "srv" / "data"
        mounted_path.mkdir(parents=True)

        def glob_side_effect(pattern):
            if pattern == "/tmp/sshfs_mount_*":
                return []
            return [str(mounted_root)]

        with (
            patch("glob.glob", side_effect=glob_side_effect),
            patch.object(
                mount_service,
                "_get_active_mount_points",
                return_value={str(mounted_path)},
            ),
        ):
            mount_service._cleanup_orphaned_temp_dirs()

        assert mounted_root.exists()

    def test_list_mounts(self, mount_service):
        """Test listing active mounts"""
        # Initially empty
        assert mount_service.list_mounts() == []

        # Add mock mount
        mount_info = MountInfo(
            mount_id="test-123",
            mount_type=MountType.BORG_ARCHIVE,
            mount_point="/tmp/test_mount",
            source="repo::archive",
            created_at=datetime.now(timezone.utc),
        )
        mount_service.active_mounts["test-123"] = mount_info

        # List should return it
        mounts = mount_service.list_mounts()
        assert len(mounts) == 1
        assert mounts[0].mount_id == "test-123"

    def test_get_mount(self, mount_service):
        """Test getting mount by ID"""
        # Initially None
        assert mount_service.get_mount("nonexistent") is None

        # Add mock mount
        mount_info = MountInfo(
            mount_id="test-123",
            mount_type=MountType.BORG_ARCHIVE,
            mount_point="/tmp/test_mount",
            source="repo::archive",
            created_at=datetime.now(timezone.utc),
        )
        mount_service.active_mounts["test-123"] = mount_info

        # Get should return it
        result = mount_service.get_mount("test-123")
        assert result is not None
        assert result.mount_id == "test-123"

    def test_cleanup_managed_mount_dir_removes_empty_directory(self, mount_service):
        managed_mount = (
            mount_service.mount_base_dir / "manual-backup-2026-01-15T16_24_12"
        )
        managed_mount.mkdir()

        mount_service._cleanup_managed_mount_dir(str(managed_mount))

        assert not managed_mount.exists()

    def test_cleanup_orphaned_mount_dirs_removes_only_untracked_empty_dirs(
        self, mount_service
    ):
        orphaned_mount = (
            mount_service.mount_base_dir / "manual-backup-2026-01-15T16_24_12"
        )
        orphaned_mount.mkdir()

        active_mount = mount_service.mount_base_dir / "still-mounted"
        active_mount.mkdir()

        tracked_mount = mount_service.mount_base_dir / "tracked-but-not-mounted"
        tracked_mount.mkdir()
        mount_service.active_mounts["tracked"] = MountInfo(
            mount_id="tracked",
            mount_type=MountType.BORG_ARCHIVE,
            mount_point=str(tracked_mount),
            source="repo::archive",
            created_at=datetime.now(timezone.utc),
        )

        with patch.object(
            mount_service,
            "_get_active_mount_points",
            return_value={str(active_mount.resolve())},
        ):
            mount_service._cleanup_orphaned_mount_dirs()

        assert not orphaned_mount.exists()
        assert active_mount.exists()
        assert tracked_mount.exists()

    @pytest.mark.asyncio
    async def test_mount_ssh_directory_no_connection(self, mount_service):
        """Test mount_ssh_directory fails gracefully when connection not found"""
        with patch("app.services.mount_service.SessionLocal") as mock_session:
            mock_db = Mock()
            mock_db.query.return_value.filter.return_value.first.return_value = None
            mock_session.return_value = mock_db

            with pytest.raises(Exception, match="SSH connection .* not found"):
                await mount_service.mount_ssh_directory(
                    connection_id=999, remote_path="/remote/path", job_id=1
                )

    @pytest.mark.asyncio
    async def test_mount_borg_archive_no_repository(self, mount_service):
        """Test mount_borg_archive fails gracefully when repository not found"""
        with patch("app.services.mount_service.SessionLocal") as mock_session:
            mock_db = Mock()
            mock_db.query.return_value.filter.return_value.first.return_value = None
            mock_session.return_value = mock_db

            with pytest.raises(Exception, match="Repository .* not found"):
                await mount_service.mount_borg_archive(
                    repository_id=999, archive_name="test-archive"
                )

    @pytest.mark.asyncio
    async def test_mount_borg_archive_sets_remote_path(self, mount_service):
        """Test that mount_borg_archive passes --remote-path flag when repository has remote_path"""
        with (
            patch("app.services.mount_service.SessionLocal") as mock_session,
            patch(
                "app.services.mount_service.asyncio.create_subprocess_exec"
            ) as mock_exec,
            patch("app.services.mount_service.os.makedirs"),
            patch("app.services.mount_service.os.path.exists", return_value=False),
            patch.dict("os.environ", {}, clear=True),
        ):
            mock_db = Mock()
            mock_session.return_value = mock_db

            # SystemSettings query returns None (uses default timeout)
            mock_repo = Mock(spec=Repository)
            mock_repo.id = 1
            mock_repo.name = "test-repo"
            mock_repo.path = "/backup/repo"
            mock_repo.passphrase = None
            mock_repo.connection_id = None
            mock_repo.bypass_lock = False
            mock_repo.remote_path = "borg14"

            # First query (Repository) returns mock_repo, second (SystemSettings) returns None
            mock_db.query.return_value.filter.return_value.first.side_effect = [
                mock_repo,
                None,
            ]
            mock_db.query.return_value.first.return_value = None

            captured_args = []

            async def fake_exec(*args, **kwargs):
                captured_args.extend(args)
                proc = AsyncMock()
                proc.pid = 12345
                proc.stdout = AsyncMock()
                proc.stdout.readline = AsyncMock(return_value=b"")
                proc.stderr = AsyncMock()
                proc.stderr.read = AsyncMock(return_value=b"")
                proc.wait = AsyncMock(return_value=0)
                return proc

            mock_exec.side_effect = fake_exec

            try:
                await mount_service.mount_borg_archive(
                    repository_id=1, archive_name="test-archive"
                )
            except Exception:
                pass

            assert mock_exec.called, "create_subprocess_exec was not called"
            assert "--remote-path" in captured_args
            assert "borg14" in captured_args

    @pytest.mark.asyncio
    async def test_mount_borg_archive_no_remote_path(self, mount_service):
        """Test that mount_borg_archive omits --remote-path when repository has no remote_path"""
        with (
            patch("app.services.mount_service.SessionLocal") as mock_session,
            patch(
                "app.services.mount_service.asyncio.create_subprocess_exec"
            ) as mock_exec,
            patch("app.services.mount_service.os.makedirs"),
            patch("app.services.mount_service.os.path.exists", return_value=False),
            patch.dict("os.environ", {}, clear=True),
        ):
            mock_db = Mock()
            mock_session.return_value = mock_db

            mock_repo = Mock(spec=Repository)
            mock_repo.id = 1
            mock_repo.name = "test-repo"
            mock_repo.path = "/backup/repo"
            mock_repo.passphrase = None
            mock_repo.connection_id = None
            mock_repo.bypass_lock = False
            mock_repo.remote_path = None

            mock_db.query.return_value.filter.return_value.first.side_effect = [
                mock_repo,
                None,
            ]
            mock_db.query.return_value.first.return_value = None

            captured_args = []

            async def fake_exec(*args, **kwargs):
                captured_args.extend(args)
                proc = AsyncMock()
                proc.pid = 12345
                proc.stdout = AsyncMock()
                proc.stdout.readline = AsyncMock(return_value=b"")
                proc.stderr = AsyncMock()
                proc.stderr.read = AsyncMock(return_value=b"")
                proc.wait = AsyncMock(return_value=0)
                return proc

            mock_exec.side_effect = fake_exec

            try:
                await mount_service.mount_borg_archive(
                    repository_id=1, archive_name="test-archive"
                )
            except Exception:
                pass

            assert mock_exec.called, "create_subprocess_exec was not called"
            assert "--remote-path" not in captured_args

    @pytest.mark.asyncio
    async def test_unmount_not_found(self, mount_service):
        """Test unmount returns False for non-existent mount"""
        result = await mount_service.unmount("nonexistent-mount-id")
        assert result is False

    @pytest.mark.asyncio
    async def test_mount_ssh_paths_shared_preserves_temp_resources_during_remount(
        self, mount_service
    ):
        """Test child mount replacement does not delete the shared temp root or SSH key"""
        with patch("app.services.mount_service.SessionLocal") as mock_session:
            mock_db = Mock()
            mock_session.return_value = mock_db

            mock_connection = Mock(spec=SSHConnection)
            mock_connection.id = 1
            mock_connection.host = "example.com"
            mock_connection.username = "tester"
            mock_connection.port = 22
            mock_connection.ssh_key_id = 10

            mock_key = Mock(spec=SSHKey)
            mock_key.id = 10

            def query_side_effect(model):
                mock_query = Mock()
                if model == SSHConnection:
                    mock_query.filter.return_value.first.return_value = mock_connection
                elif model == SSHKey:
                    mock_query.filter.return_value.first.return_value = mock_key
                return mock_query

            mock_db.query.side_effect = query_side_effect

            temp_key = tempfile.NamedTemporaryFile(delete=False, suffix=".key")
            temp_key.close()

            mount_calls = []

            async def mock_execute_mount(
                connection,
                remote_path,
                mount_point,
                temp_key_file,
                preserve_symlinks=False,
            ):
                assert os.path.exists(mount_point)
                assert os.path.exists(temp_key_file)
                mount_calls.append((remote_path, mount_point))

            try:
                with (
                    patch.object(
                        mount_service, "_check_sshfs_available", return_value=True
                    ),
                    patch.object(
                        mount_service,
                        "_decrypt_and_write_key",
                        return_value=temp_key.name,
                    ),
                    patch.object(
                        mount_service,
                        "_check_remote_is_file",
                        side_effect=[False, True],
                    ),
                    patch.object(
                        mount_service, "_execute_sshfs_mount", new_callable=AsyncMock
                    ) as mock_mount,
                    patch.object(
                        mount_service, "_verify_mount_readable", new_callable=AsyncMock
                    ),
                    patch.object(
                        mount_service,
                        "_unmount_fuse",
                        new_callable=AsyncMock,
                        return_value=True,
                    ),
                    patch.object(mount_service, "_save_state"),
                ):
                    mock_mount.side_effect = mock_execute_mount

                    (
                        temp_root,
                        mount_info_list,
                    ) = await mount_service.mount_ssh_paths_shared(
                        connection_id=1,
                        remote_paths=["/home/tester/docs", "/home/tester/file.txt"],
                        job_id=42,
                    )

                    assert len(mount_calls) == 2
                    assert mount_calls[0][0] == "/home/tester/docs"
                    assert mount_calls[1][0] == "/home/tester"

                    assert os.path.exists(temp_root)
                    assert os.path.exists(temp_key.name)
                    assert len(mount_service.active_mounts) == 1
                    assert len(set(mount_id for mount_id, _ in mount_info_list)) == 1

                    final_mount = next(iter(mount_service.active_mounts.values()))
                    assert final_mount.mount_point == os.path.join(
                        temp_root, "home/tester"
                    )
            finally:
                mount_service._cleanup_temp_files(
                    next(iter(mount_service.active_mounts.values())).temp_root
                    if mount_service.active_mounts
                    else None,
                    temp_key.name if os.path.exists(temp_key.name) else None,
                )
                mount_service.active_mounts.clear()

    @pytest.mark.asyncio
    async def test_execute_sshfs_mount_retries_login_relative_path_when_absolute_missing(
        self, mount_service
    ):
        connection = Mock(spec=SSHConnection)
        connection.host = "192.168.1.150"
        connection.username = "karanhudia"
        connection.port = 22
        connection.use_sudo = False
        connection.default_path = "/"

        first_process = AsyncMock()
        first_process.returncode = 1
        first_process.communicate = AsyncMock(
            return_value=(
                b"",
                b"karanhudia@192.168.1.150:/test-backup-source: No such file or directory\n",
            )
        )
        second_process = AsyncMock()
        second_process.returncode = 0
        second_process.communicate = AsyncMock(return_value=(b"", b""))

        with (
            patch(
                "app.services.mount_service.asyncio.create_subprocess_exec",
                new=AsyncMock(side_effect=[first_process, second_process]),
            ) as mock_exec,
            patch("app.services.mount_service.asyncio.sleep", new=AsyncMock()),
        ):
            await mount_service._execute_sshfs_mount(
                connection=connection,
                remote_path="/test-backup-source",
                mount_point="/tmp/sshfs_mount_378/test-backup-source",
                temp_key_file="/tmp/test.key",
            )

        assert mock_exec.await_count == 2
        first_cmd = mock_exec.await_args_list[0].args
        second_cmd = mock_exec.await_args_list[1].args
        assert first_cmd[1] == "karanhudia@192.168.1.150:/test-backup-source"
        assert second_cmd[1] == "karanhudia@192.168.1.150:test-backup-source"

    @pytest.mark.asyncio
    async def test_execute_sshfs_mount_does_not_retry_relative_path_for_explicit_default_path(
        self, mount_service
    ):
        connection = Mock(spec=SSHConnection)
        connection.host = "192.168.1.150"
        connection.username = "karanhudia"
        connection.port = 22
        connection.use_sudo = False
        connection.default_path = "/home/karanhudia"

        process = AsyncMock()
        process.returncode = 1
        process.communicate = AsyncMock(
            return_value=(
                b"",
                b"karanhudia@192.168.1.150:/missing: No such file or directory\n",
            )
        )

        with (
            patch(
                "app.services.mount_service.asyncio.create_subprocess_exec",
                new=AsyncMock(return_value=process),
            ) as mock_exec,
            patch("app.services.mount_service.asyncio.sleep", new=AsyncMock()),
            pytest.raises(Exception, match="SSHFS mount failed"),
        ):
            await mount_service._execute_sshfs_mount(
                connection=connection,
                remote_path="/missing",
                mount_point="/tmp/sshfs_mount_378/missing",
                temp_key_file="/tmp/test.key",
            )

        assert mock_exec.await_count == 1

    @pytest.mark.skip(
        reason="_verify_mount_writable() method not yet implemented - planned feature"
    )
    @pytest.mark.asyncio
    async def test_verify_mount_writable_success(self, mount_service):
        """Test mount verification with writable mount"""
        # Create a real temp directory
        temp_dir = tempfile.mkdtemp()

        try:
            # Should succeed without raising
            await mount_service._verify_mount_writable(temp_dir)
        finally:
            # Cleanup
            import shutil

            shutil.rmtree(temp_dir, ignore_errors=True)

    @pytest.mark.skip(
        reason="_verify_mount_writable() method not yet implemented - planned feature"
    )
    @pytest.mark.asyncio
    async def test_verify_mount_writable_failure(self, mount_service):
        """Test mount verification with non-writable mount"""
        # Use a non-existent directory
        with pytest.raises(Exception, match="Mount verification failed"):
            await mount_service._verify_mount_writable("/nonexistent/mount/point")


@pytest.mark.unit
class TestMountInfo:
    """Test MountInfo dataclass"""

    def test_mount_info_creation(self):
        """Test MountInfo creation"""
        now = datetime.now(timezone.utc)
        info = MountInfo(
            mount_id="test-123",
            mount_type=MountType.SSHFS,
            mount_point="/tmp/mount",
            source="ssh://user@host/path",
            created_at=now,
            job_id=42,
        )

        assert info.mount_id == "test-123"
        assert info.mount_type == MountType.SSHFS
        assert info.mount_point == "/tmp/mount"
        assert info.source == "ssh://user@host/path"
        assert info.created_at == now
        assert info.job_id == 42

    def test_mount_info_optional_fields(self):
        """Test MountInfo with optional fields"""
        info = MountInfo(
            mount_id="test-123",
            mount_type=MountType.BORG_ARCHIVE,
            mount_point="/tmp/mount",
            source="repo::archive",
            created_at=datetime.now(timezone.utc),
        )

        # Optional fields should be None by default
        assert info.job_id is None
        assert info.temp_root is None
        assert info.temp_key_file is None
        assert info.connection_id is None
        assert info.repository_id is None


@pytest.mark.unit
class TestMountRoleGuard:
    """Viewers must be blocked from all mutating mount endpoints."""

    def test_viewer_cannot_mount(self, test_client, auth_headers):
        response = test_client.post(
            "/api/mounts/borg",
            json={"repository_id": 1},
            headers=auth_headers,
        )
        assert response.status_code == 403
        assert (
            response.json()["detail"]["key"]
            == "backend.errors.mounts.operatorAccessRequired"
        )

    def test_viewer_cannot_unmount(self, test_client, auth_headers):
        response = test_client.post(
            "/api/mounts/borg/unmount/fake-mount-id",
            headers=auth_headers,
        )
        assert response.status_code == 403
        assert (
            response.json()["detail"]["key"]
            == "backend.errors.mounts.operatorAccessRequired"
        )

    def test_viewer_cannot_force_unmount(self, test_client, auth_headers):
        response = test_client.post(
            "/api/mounts/borg/unmount/fake-mount-id?force=true",
            headers=auth_headers,
        )
        assert response.status_code == 403
        assert (
            response.json()["detail"]["key"]
            == "backend.errors.mounts.operatorAccessRequired"
        )

    def test_viewer_can_list_mounts(self, test_client, auth_headers):
        """Read endpoints must remain accessible to viewers."""
        response = test_client.get("/api/mounts", headers=auth_headers)
        assert response.status_code == 200
