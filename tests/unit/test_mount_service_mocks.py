
import pytest
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock, call
from app.services.mount_service import MountService, MountType, MountInfo
from app.database.models import Repository, SSHConnection, SSHKey, SystemSettings

@pytest.fixture
def mock_db_session():
    """Mock database session"""
    session = MagicMock()
    # Mock query chain
    session.query.return_value.filter.return_value.first.return_value = None
    session.query.return_value.first.return_value = None
    return session

@pytest.fixture
def mock_settings():
    """Mock system settings"""
    settings = MagicMock(spec=SystemSettings)
    settings.mount_timeout = 10  # Short timeout for tests
    settings.data_dir = "/tmp/borg-data"
    settings.secret_key = "test_secret_key_32_chars_long_exactly"
    return settings

@pytest.fixture
def mount_service_fixture(mock_db_session):
    """Create MountService instance with mocked dependencies"""
    with patch("app.services.mount_service.settings") as mock_conf:
        mock_conf.data_dir = "/tmp/borg-data"
        mock_conf.secret_key = "test_secret_key_32_chars_long_exactly"
        
        # Don't patch Path, use real paths
        with patch("app.services.mount_service.subprocess.run") as mock_run:
            # Mock initial cleanup check
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = ""
            
            with patch("app.services.mount_service.os.makedirs"): # Prevent real dir creation
                service = MountService()
                # Inject mock session factory
                with patch("app.services.mount_service.SessionLocal", return_value=mock_db_session):
                    yield service

@pytest.mark.asyncio
async def test_mount_borg_archive_success(mount_service_fixture, mock_db_session):
    """Test successful Borg archive mount"""
    # Setup Data
    repo = Repository(id=1, name="TestRepo", path="/backups/repo", repository_type="local")
    
    # Needs timeout > 5s because code hardcodes 5s sleep interval
    mock_db_session.query.return_value.filter.return_value.first.return_value = repo
    mock_db_session.query.return_value.first.return_value = SystemSettings(mount_timeout=10)

    # Mock DB query filter for repo and settings
    def query_side_effect(model):
        m = MagicMock()
        if model == Repository:
            m.filter.return_value.first.return_value = repo
        elif model == SystemSettings:
            m.first.return_value = SystemSettings(mount_timeout=10)
            m.filter.return_value.all.return_value = []
        return m
    mock_db_session.query.side_effect = query_side_effect

    # Mock subprocess creation for 'borg mount'
    mock_process = AsyncMock()
    mock_process.pid = 12345
    mock_process.returncode = None # Running
    mock_process.kill = MagicMock() # Sync method
    
    # Mock sleep to be instant
    with patch("app.services.mount_service.asyncio.sleep", return_value=None):
        with patch("app.services.mount_service.asyncio.create_subprocess_exec", return_value=mock_process) as mock_exec:
            with patch("app.services.mount_service.subprocess.run") as mock_run:
                # First check for cleanup (empty)
                # Second check for verification (success)
                # Expect 'repository' because archive_name is None
                expected_mount_point = "/tmp/borg-data/mounts/repository"
                
                mock_run.side_effect = [
                    MagicMock(returncode=0, stdout=""), # Cleanup check
                    MagicMock(returncode=0, stdout=f"{expected_mount_point} on {expected_mount_point}") # Verification
                ]
                
                with patch("app.services.mount_service.os.makedirs"):
                    with patch("app.services.mount_service.os.path.exists", return_value=False):
                         # EXECUTE
                        path, mount_id = await mount_service_fixture.mount_borg_archive(repository_id=1)

                        # VERIFY
                        assert path.endswith("repository")
                        assert mount_id in mount_service_fixture.active_mounts
                        
                        # Verify command
                        args = mock_exec.call_args[0]
                        assert args[0] == "borg"
                        assert args[1] == "mount"
                        assert "/backups/repo" in args
                        assert "-f" in args # Foreground mode


@pytest.mark.asyncio
async def test_mount_borg_archive_uses_borg2_binary_for_v2_repo(mount_service_fixture, mock_db_session):
    repo = Repository(
        id=1,
        name="TestRepo",
        path="/backups/repo",
        repository_type="local",
        borg_version=2,
    )

    def query_side_effect(model):
        m = MagicMock()
        if model == Repository:
            m.filter.return_value.first.return_value = repo
        elif model == SystemSettings:
            m.first.return_value = SystemSettings(mount_timeout=10)
            m.filter.return_value.all.return_value = []
        return m

    mock_db_session.query.side_effect = query_side_effect
    mock_process = AsyncMock()
    mock_process.pid = 12345
    mock_process.returncode = None
    mock_process.kill = MagicMock()

    with patch("app.services.mount_service.asyncio.sleep", return_value=None), patch(
        "app.core.borg2.borg2.borg_cmd", "borg2"
    ), patch(
        "app.services.mount_service.asyncio.create_subprocess_exec", return_value=mock_process
    ) as mock_exec, patch("app.services.mount_service.subprocess.run") as mock_run, patch(
        "app.services.mount_service.os.makedirs"
    ), patch("app.services.mount_service.os.path.exists", return_value=False):
        expected_mount_point = "/tmp/borg-data/mounts/repository"
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout=""),
            MagicMock(returncode=0, stdout=f"{expected_mount_point} on {expected_mount_point}"),
        ]

        _, mount_id = await mount_service_fixture.mount_borg_archive(repository_id=1)

    args = mock_exec.call_args[0]
    assert args[0] == "borg2"
    assert "-r" in args
    assert "mount" in args
    mount_index = args.index("mount")
    assert args[mount_index + 1] == expected_mount_point
    assert mount_service_fixture.active_mounts[mount_id].borg_version == 2

@pytest.mark.asyncio
async def test_unmount_success(mount_service_fixture):
    """Test successful unmount"""
    # Setup active mount
    mount_id = "test-mount-id"
    mount_info = MountInfo(
        mount_id=mount_id,
        mount_type=MountType.BORG_ARCHIVE,
        mount_point="/mnt/test",
        source="repo",
        created_at="2024-01-01",
        process_pid=12345
    )
    mount_service_fixture.active_mounts[mount_id] = mount_info

    # Mock process killing and unmount command
    # _unmount_borg uses asyncio.create_subprocess_exec
    mock_process = AsyncMock()
    mock_process.returncode = 0
    mock_process.communicate.return_value = (b"", b"")

    with patch("app.services.mount_service.os.kill") as mock_kill:
        with patch("app.services.mount_service.asyncio.create_subprocess_exec", return_value=mock_process):
            
            # EXECUTE
            result = await mount_service_fixture.unmount(mount_id)

            # VERIFY
            assert result is True
            assert mount_id not in mount_service_fixture.active_mounts
            
            # Verify PID verify/kill flow
            mock_kill.assert_any_call(12345, 15)


@pytest.mark.asyncio
async def test_unmount_v2_uses_borg2_binary(mount_service_fixture):
    mount_id = "test-mount-id"
    mount_service_fixture.active_mounts[mount_id] = MountInfo(
        mount_id=mount_id,
        mount_type=MountType.BORG_ARCHIVE,
        mount_point="/mnt/test",
        source="repo",
        created_at="2024-01-01",
        borg_version=2,
        process_pid=12345,
    )

    mock_process = AsyncMock()
    mock_process.returncode = 0
    mock_process.communicate.return_value = (b"", b"")

    with patch("app.services.mount_service.os.kill"), patch(
        "app.core.borg2.borg2.borg_cmd", "borg2"
    ), patch(
        "app.services.mount_service.asyncio.create_subprocess_exec", return_value=mock_process
    ) as mock_exec:
        result = await mount_service_fixture.unmount(mount_id)

    assert result is True
    args = mock_exec.call_args[0]
    assert args[0] == "borg2"
    assert args[1] == "umount"

@pytest.mark.asyncio
async def test_list_mounts(mount_service_fixture):
    """Test listing mounts"""
    mount_id = "test-id"
    mount_service_fixture.active_mounts[mount_id] = MountInfo(
        mount_id=mount_id,
        mount_type=MountType.BORG_ARCHIVE,
        mount_point="/mnt/test",
        source="repo",
        created_at="NOW"
    )
    
    mounts = mount_service_fixture.list_mounts()
    assert len(mounts) == 1
    assert mounts[0].mount_id == mount_id

def _make_sshfs_connection(use_sudo: bool) -> SSHConnection:
    """Build a minimal SSHConnection for SSHFS tests."""
    return SSHConnection(
        id=1,
        host="backup-host.example.com",
        username="backupuser",
        port=22,
        ssh_key_id=1,
        status="connected",
        use_sudo=use_sudo,
    )


def _make_subprocess_mocks(sftp_server_line: str = "sftp_server=/usr/lib/openssh/sftp-server"):
    """
    Return (diag_proc, sshfs_proc, captured_commands).

    diag_proc  – mock for the diagnostic SSH call that reports the sftp-server path.
    sshfs_proc – mock for the actual SSHFS mount call (returns None returncode so
                 no error is raised, simulating SSHFS forking to background).
    captured_commands – list that is filled by the side_effect with every
                        positional-args tuple passed to create_subprocess_exec.
    """
    diag_out = (
        f"user=backupuser\nuid=1001\ngroups=backupuser\nsudo=yes\n{sftp_server_line}"
    ).encode()

    diag_proc = AsyncMock()
    diag_proc.communicate = AsyncMock(return_value=(diag_out, b""))

    sshfs_proc = AsyncMock()
    sshfs_proc.returncode = None  # SSHFS forks; returncode=None means no error
    sshfs_proc.communicate = AsyncMock(return_value=(b"", b""))

    captured_commands: list = []

    async def capture_exec(*args, **kwargs):
        captured_commands.append(list(args))
        return diag_proc if args[0] == "ssh" else sshfs_proc

    return diag_proc, sshfs_proc, captured_commands, capture_exec


@pytest.mark.asyncio
async def test_sshfs_includes_sudo_sftp_server_option_when_use_sudo_true(mount_service_fixture):
    """
    When the SSH connection has use_sudo=True the SSHFS command must include
    '-o sftp_server=sudo <path>' so the remote sftp-server runs with elevated
    privileges and can read root-owned files.
    """
    connection = _make_sshfs_connection(use_sudo=True)
    _, _, captured_commands, capture_exec = _make_subprocess_mocks(
        sftp_server_line="sftp_server=/usr/lib/openssh/sftp-server"
    )

    with patch("app.services.mount_service.asyncio.create_subprocess_exec", side_effect=capture_exec):
        with patch("app.services.mount_service.asyncio.sleep", return_value=None):
            await mount_service_fixture._execute_sshfs_mount(
                connection=connection,
                remote_path="/remote/data",
                mount_point="/tmp/mounts/test",
                temp_key_file="/tmp/test_key",
            )

    sshfs_cmd = next((cmd for cmd in captured_commands if cmd[0] == "sshfs"), None)
    assert sshfs_cmd is not None, "sshfs command was not called"
    cmd_flat = " ".join(sshfs_cmd)
    assert "sftp_server=sudo /usr/lib/openssh/sftp-server" in cmd_flat, (
        f"expected sudo sftp-server option in sshfs command, got:\n{cmd_flat}"
    )


@pytest.mark.asyncio
async def test_sshfs_omits_sudo_sftp_server_option_when_use_sudo_false(mount_service_fixture):
    """
    When use_sudo=False the SSHFS command must NOT include a sftp_server override –
    the remote sftp-server runs as the authenticated user with no privilege elevation.
    """
    connection = _make_sshfs_connection(use_sudo=False)
    _, _, captured_commands, capture_exec = _make_subprocess_mocks()

    with patch("app.services.mount_service.asyncio.create_subprocess_exec", side_effect=capture_exec):
        with patch("app.services.mount_service.asyncio.sleep", return_value=None):
            await mount_service_fixture._execute_sshfs_mount(
                connection=connection,
                remote_path="/remote/data",
                mount_point="/tmp/mounts/test",
                temp_key_file="/tmp/test_key",
            )

    sshfs_cmd = next((cmd for cmd in captured_commands if cmd[0] == "sshfs"), None)
    assert sshfs_cmd is not None, "sshfs command was not called"
    cmd_flat = " ".join(sshfs_cmd)
    assert "sftp_server=" not in cmd_flat, (
        f"sftp_server option must be absent when use_sudo=False, got:\n{cmd_flat}"
    )


@pytest.mark.asyncio
async def test_sshfs_sudo_falls_back_to_default_sftp_server_when_diagnostic_fails(
    mount_service_fixture,
):
    """
    When use_sudo=True but the SSH diagnostic cannot determine the sftp-server path
    (empty line), the SSHFS command must fall back to '/usr/lib/openssh/sftp-server'
    so the mount still succeeds rather than silently dropping the sudo option.
    """
    connection = _make_sshfs_connection(use_sudo=True)
    # Diagnostic returns an empty sftp_server value
    _, _, captured_commands, capture_exec = _make_subprocess_mocks(
        sftp_server_line="sftp_server="
    )

    with patch("app.services.mount_service.asyncio.create_subprocess_exec", side_effect=capture_exec):
        with patch("app.services.mount_service.asyncio.sleep", return_value=None):
            await mount_service_fixture._execute_sshfs_mount(
                connection=connection,
                remote_path="/remote/data",
                mount_point="/tmp/mounts/test",
                temp_key_file="/tmp/test_key",
            )

    sshfs_cmd = next((cmd for cmd in captured_commands if cmd[0] == "sshfs"), None)
    assert sshfs_cmd is not None, "sshfs command was not called"
    cmd_flat = " ".join(sshfs_cmd)
    assert "sftp_server=sudo /usr/lib/openssh/sftp-server" in cmd_flat, (
        f"expected fallback sftp-server path in sshfs command, got:\n{cmd_flat}"
    )


@pytest.mark.asyncio
async def test_cleanup_stale_mounts(mount_service_fixture):
    """Test cleanup of stale mounts on init"""
    # Manually seed a stale mount
    mount_id = "stale-id"
    mount_service_fixture.active_mounts[mount_id] = MountInfo(
        mount_id=mount_id,
        mount_type=MountType.BORG_ARCHIVE,
        mount_point="/mnt/stale",
        source="repo",
        created_at="OLD"
    )
    
    with patch("app.services.mount_service.subprocess.run") as mock_run:
        # Return list of system mounts that DOES NOT include /mnt/stale
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "/dev/sda1 on /\n/mnt/active on /mnt/active"
        
        # Call cleanup
        mount_service_fixture._cleanup_stale_mounts()
        
        # Verify stale mount is removed
        assert mount_id not in mount_service_fixture.active_mounts
