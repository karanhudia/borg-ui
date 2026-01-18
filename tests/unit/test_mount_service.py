"""
Unit tests for MountService
"""
import pytest
import tempfile
import os
from pathlib import Path
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from datetime import datetime, timezone

from app.services.mount_service import MountService, MountType, MountInfo
from app.database.models import SSHConnection, SSHKey, Repository


@pytest.mark.unit
class TestMountService:
    """Test MountService class methods"""

    @pytest.fixture
    def mount_service(self):
        """Create a MountService instance"""
        with patch('app.services.mount_service.settings') as mock_settings:
            mock_settings.data_dir = tempfile.mkdtemp()
            mock_settings.secret_key = "test_secret_key_32_characters!"
            service = MountService()
            yield service

    def test_init(self, mount_service):
        """Test MountService initialization"""
        assert mount_service is not None
        assert mount_service.active_mounts == {}
        assert mount_service.mount_base_dir.exists()

    def test_validate_mount_point_sensitive_paths(self, mount_service):
        """Test mount point validation rejects sensitive system paths"""
        sensitive_paths = ['/etc', '/root', '/sys', '/proc', '/boot', '/dev', '/var', '/usr']

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
        valid_paths = ['/tmp/mount', '/home/user/mount', '/mnt/data']

        for path in valid_paths:
            # Should not raise exception
            mount_service._validate_mount_point(path)

    @pytest.mark.asyncio
    async def test_check_sshfs_available_found(self, mount_service):
        """Test SSHFS availability check when installed"""
        with patch('asyncio.create_subprocess_exec') as mock_exec:
            mock_process = AsyncMock()
            mock_process.communicate = AsyncMock(return_value=(b'', b''))
            mock_process.returncode = 0
            mock_exec.return_value = mock_process

            result = await mount_service._check_sshfs_available()
            assert result is True

    @pytest.mark.asyncio
    async def test_check_sshfs_available_not_found(self, mount_service):
        """Test SSHFS availability check when not installed"""
        with patch('asyncio.create_subprocess_exec') as mock_exec:
            mock_process = AsyncMock()
            mock_process.communicate = AsyncMock(return_value=(b'', b''))
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
        with patch('app.services.mount_service.Fernet') as mock_fernet_class:
            mock_cipher = Mock()
            mock_cipher.decrypt.return_value = test_private_key.encode()
            mock_fernet_class.return_value = mock_cipher

            mock_ssh_key.private_key = "mock_encrypted_key"

            with patch('app.services.mount_service.settings') as mock_settings:
                mock_settings.secret_key = "test_secret_key_32_chars!!!!!"

                # Test key file creation
                temp_key_file = mount_service._decrypt_and_write_key(mock_ssh_key)

                try:
                    # Verify file exists
                    assert os.path.exists(temp_key_file)

                    # Verify permissions are 0o600
                    stat_info = os.stat(temp_key_file)
                    assert oct(stat_info.st_mode)[-3:] == '600'

                    # Verify content (with trailing newline added by the method)
                    with open(temp_key_file, 'r') as f:
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
        temp_key_file = tempfile.NamedTemporaryFile(delete=False, suffix='.key').name

        # Verify they exist
        assert os.path.exists(temp_root)
        assert os.path.exists(temp_key_file)

        # Cleanup
        mount_service._cleanup_temp_files(temp_root, temp_key_file)

        # Verify they're gone
        assert not os.path.exists(temp_root)
        assert not os.path.exists(temp_key_file)

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
            created_at=datetime.now(timezone.utc)
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
            created_at=datetime.now(timezone.utc)
        )
        mount_service.active_mounts["test-123"] = mount_info

        # Get should return it
        result = mount_service.get_mount("test-123")
        assert result is not None
        assert result.mount_id == "test-123"

    @pytest.mark.asyncio
    async def test_mount_ssh_directory_no_connection(self, mount_service):
        """Test mount_ssh_directory fails gracefully when connection not found"""
        with patch('app.services.mount_service.SessionLocal') as mock_session:
            mock_db = Mock()
            mock_db.query.return_value.filter.return_value.first.return_value = None
            mock_session.return_value = mock_db

            with pytest.raises(Exception, match="SSH connection .* not found"):
                await mount_service.mount_ssh_directory(
                    connection_id=999,
                    remote_path="/remote/path",
                    job_id=1
                )

    @pytest.mark.asyncio
    async def test_mount_borg_archive_no_repository(self, mount_service):
        """Test mount_borg_archive fails gracefully when repository not found"""
        with patch('app.services.mount_service.SessionLocal') as mock_session:
            mock_db = Mock()
            mock_db.query.return_value.filter.return_value.first.return_value = None
            mock_session.return_value = mock_db

            with pytest.raises(Exception, match="Repository .* not found"):
                await mount_service.mount_borg_archive(
                    repository_id=999,
                    archive_name="test-archive"
                )

    @pytest.mark.asyncio
    async def test_unmount_not_found(self, mount_service):
        """Test unmount returns False for non-existent mount"""
        result = await mount_service.unmount("nonexistent-mount-id")
        assert result is False

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
            job_id=42
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
            created_at=datetime.now(timezone.utc)
        )

        # Optional fields should be None by default
        assert info.job_id is None
        assert info.temp_root is None
        assert info.temp_key_file is None
        assert info.connection_id is None
        assert info.repository_id is None
