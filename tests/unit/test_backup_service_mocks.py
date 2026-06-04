import json
import pytest
from unittest.mock import MagicMock, patch, AsyncMock, Mock
from app.services.backup_service import BackupService
from app.database.models import (
    BackupJob,
    Repository,
    RepositoryStorage,
    SystemSettings,
    RepositoryScript,
    SSHConnection,
)


@pytest.fixture
def mock_db_session():
    """Mock database session"""
    session = MagicMock()
    # Default mocks to avoid NoneType errors
    session.query.return_value.filter.return_value.first.return_value = None
    return session


@pytest.fixture
def backup_service_fixture(mock_db_session):
    """Create BackupService instance with mocked dependencies"""
    with patch("app.services.backup_service.settings") as mock_conf:
        mock_conf.data_dir = "/tmp/borg-data"
        mock_conf.backup_timeout = 3600
        mock_conf.script_timeout = 60  # Fix for size calculation
        mock_conf.borg_info_timeout = 60
        mock_conf.borg_list_timeout = 60
        mock_conf.source_size_timeout = 120

        with patch("app.services.backup_service.Path") as mock_path:
            # Mock filesystem paths
            mock_path.return_value.exists.return_value = True
            mock_path.return_value.mkdir.return_value = None

            service = BackupService()
            yield service


def _notification_service_mock():
    notifications = MagicMock()
    notifications.send_backup_failure = AsyncMock()
    notifications.send_backup_start = AsyncMock()
    notifications.send_backup_success = AsyncMock()
    notifications.send_backup_warning = AsyncMock()
    return notifications


def test_resolve_backup_command_paths_uses_shared_cwd_for_mixed_ssh_and_local(
    backup_service_fixture,
):
    backup_paths, backup_cwd = backup_service_fixture._resolve_backup_command_paths(
        ["home/app/data", "var/lib/service", "/srv/app"],
        [
            ("/tmp/sshfs_mount_42_abcd", "home/app/data"),
            ("/tmp/sshfs_mount_42_abcd", "var/lib/service"),
        ],
        job_id=42,
    )

    assert backup_cwd == "/tmp/sshfs_mount_42_abcd"
    assert backup_paths == ["home/app/data", "var/lib/service", "/srv/app"]
    assert all("/tmp/sshfs_mount_" not in path for path in backup_paths)


@pytest.mark.asyncio
async def test_prepare_source_paths_reuses_first_sshfs_temp_root_for_multiple_connections(
    backup_service_fixture, mock_db_session
):
    source_a = SSHConnection(
        id=11,
        host="server-a.example",
        username="backup-a",
        port=22,
    )
    source_b = SSHConnection(
        id=12,
        host="server-b.example",
        username="backup-b",
        port=2222,
    )

    ssh_query = MagicMock()
    ssh_query.filter.return_value.first.side_effect = [source_a, source_b]

    def query_side_effect(model):
        m = MagicMock()
        if model == SSHConnection:
            return ssh_query
        return m

    mock_db_session.query.side_effect = query_side_effect

    with (
        patch("app.services.backup_service.SessionLocal", return_value=mock_db_session),
        patch(
            "app.services.mount_service.mount_service.mount_ssh_paths_shared",
            new=AsyncMock(
                side_effect=[
                    ("/tmp/sshfs_mount_42_shared", [("mount-a", "home/app/data")]),
                    ("/tmp/sshfs_mount_42_shared", [("mount-b", "var/lib/service")]),
                ]
            ),
        ) as mount_shared,
    ):
        (
            processed_paths,
            ssh_mount_info,
        ) = await backup_service_fixture._prepare_source_paths(
            [
                "ssh://backup-a@server-a.example:22/home/app/data",
                "ssh://backup-b@server-b.example:2222/var/lib/service",
                "/srv/app",
            ],
            job_id=42,
        )

    assert processed_paths == ["home/app/data", "var/lib/service", "/srv/app"]
    assert ssh_mount_info == [
        ("/tmp/sshfs_mount_42_shared", "home/app/data"),
        ("/tmp/sshfs_mount_42_shared", "var/lib/service"),
    ]
    assert mount_shared.await_args_list[0].kwargs.get("temp_root") is None
    assert (
        mount_shared.await_args_list[1].kwargs["temp_root"]
        == "/tmp/sshfs_mount_42_shared"
    )


@pytest.mark.asyncio
async def test_execute_backup_command(
    backup_service_fixture, mock_db_session, tmp_path
):
    """Test 'borg create' command construction"""
    # Setup Data
    job_id = 999
    source_path = tmp_path / "data"
    source_path.mkdir()
    repo = Repository(
        id=1,
        path="/backups/repo",
        compression="zstd,3",
        source_directories=f'["{source_path}"]',
        exclude_patterns='["*.tmp"]',
        passphrase="secret",
        mode="full",
    )
    job = BackupJob(id=job_id, status="pending")

    def query_side_effect(model):
        m = MagicMock()
        if model == BackupJob:
            m.filter.return_value.first.return_value = job
        elif model == Repository:
            m.filter.return_value.first.return_value = repo
        elif model == SystemSettings:
            m.first.return_value = SystemSettings()
        # IMPORTANT: Mock RepositoryScript count to 0 to avoid using Library Executor logic for command test
        elif model == RepositoryScript:
            m.filter.return_value.count.return_value = 0
        return m

    mock_db_session.query.side_effect = query_side_effect

    # Mock subprocess
    mock_process = AsyncMock()
    mock_process.returncode = 0
    mock_process.stdout = AsyncMock()
    mock_process.stdout.__aiter__.return_value = iter(
        [b'{"type": "archive_progress", "original_size": 100}']
    )

    with patch(
        "app.services.backup_service.asyncio.create_subprocess_exec",
        return_value=mock_process,
    ) as mock_exec:
        with patch(
            "app.services.backup_service.SessionLocal", return_value=mock_db_session
        ):
            with patch(
                "app.services.backup_service.BorgRouter.validate_local_repository_access",
                return_value=None,
            ):
                with patch(
                    "app.services.backup_service.notification_service",
                    _notification_service_mock(),
                ):
                    # Patch hooks to avoid complexity in this specific test
                    with patch.object(
                        backup_service_fixture,
                        "_execute_hooks",
                        return_value={
                            "success": True,
                            "execution_logs": [],
                            "scripts_executed": 0,
                            "scripts_failed": 0,
                            "using_library": False,
                        },
                    ):
                        # EXECUTE
                        await backup_service_fixture.execute_backup(
                            job_id, repo.path, db=mock_db_session
                        )

                    # VERIFY
                    # Verify command arguments - search for the 'create' command in all calls
                    create_call_args = None
                    for call_args in mock_exec.call_args_list:
                        args = call_args[0]
                        if len(args) > 1 and args[0] == "borg" and args[1] == "create":
                            create_call_args = args
                            break

                    assert create_call_args is not None, (
                        "borg create command was not executed"
                    )

                    assert "--compression" in create_call_args
                    assert "zstd,3" in create_call_args
                    assert "--exclude" in create_call_args
                    assert "*.tmp" in create_call_args
                    assert str(source_path) in create_call_args  # Source path

                    # Verify content of the archive argument
                    archive_arg = [a for a in create_call_args if "::" in a][0]
                    assert archive_arg.startswith("/backups/repo::manual-backup-")


@pytest.mark.asyncio
async def test_execute_backup_hooks(backup_service_fixture, mock_db_session, tmp_path):
    """Test pre/post backup hook execution"""
    # Setup Data
    job_id = 999
    source_path = tmp_path / "data"
    source_path.mkdir()
    repo = Repository(
        id=1,
        path="/backups/repo",
        source_directories=f'["{source_path}"]',
        pre_backup_script="echo pre",
        post_backup_script="echo post",
    )
    job = BackupJob(id=job_id, status="pending")

    mock_db_session.query.return_value.filter.return_value.first.return_value = job

    # More complex query mocking for repository lookup
    def query_side_effect(model):
        m = MagicMock()
        if model == BackupJob:
            m.filter.return_value.first.return_value = job
        elif model == Repository:
            m.filter.return_value.first.return_value = repo
        elif model == SystemSettings:
            m.first.return_value = SystemSettings()
        # Mock RepositoryScript check to return empty list (force legacy inline scripts)
        elif model == RepositoryScript:
            m.filter.return_value.count.return_value = 0
        return m

    mock_db_session.query.side_effect = query_side_effect

    # Mock Script Exectuor
    mock_executor_result = {
        "success": True,
        "logs": ["executed"],
        "stdout": "",
        "stderr": "",
        "exit_code": 0,
    }

    with patch("app.services.backup_service.ScriptLibraryExecutor") as MockExecutor:
        # Properly mock async method
        instance = MockExecutor.return_value
        instance.execute_inline_script = AsyncMock(return_value=mock_executor_result)

        # Mock subprocess for actual backup - empty iterator to avoid errors
        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.stdout = AsyncMock()
        mock_process.stdout.__aiter__.return_value = iter([])

        with patch(
            "app.services.backup_service.asyncio.create_subprocess_exec",
            return_value=mock_process,
        ):
            with patch(
                "app.services.backup_service.SessionLocal", return_value=mock_db_session
            ):
                with patch(
                    "app.services.backup_service.BorgRouter.validate_local_repository_access",
                    return_value=None,
                ):
                    with patch(
                        "app.services.backup_service.notification_service",
                        _notification_service_mock(),
                    ):
                        # EXECUTE
                        await backup_service_fixture.execute_backup(
                            job_id, repo.path, db=mock_db_session
                        )

        # VERIFY Hooks called
        # Should be called once for pre-backup and once for post-backup
        assert instance.execute_inline_script.call_count == 2

        # Check first call was pre-backup
        call1 = instance.execute_inline_script.call_args_list[0]
        assert call1.kwargs["script_type"] == "pre-backup"

        # Check second call was post-backup
        call2 = instance.execute_inline_script.call_args_list[1]
        assert call2.kwargs["script_type"] == "post-backup"


@pytest.mark.asyncio
async def test_execute_backup_runs_post_hook_on_cancel_as_failure(
    backup_service_fixture, mock_db_session, tmp_path
):
    """Cancelled backups should still execute post-backup hooks with failure semantics."""
    job_id = 1001
    source_path = tmp_path / "data"
    source_path.mkdir()
    repo = Repository(
        id=1,
        path="/backups/repo",
        source_directories=f'["{source_path}"]',
        post_backup_script="echo post",
    )
    job = BackupJob(id=job_id, status="cancelled")

    def query_side_effect(model):
        m = MagicMock()
        if model == BackupJob:
            m.filter.return_value.first.return_value = job
        elif model == Repository:
            m.filter.return_value.first.return_value = repo
        elif model == SystemSettings:
            m.first.return_value = SystemSettings()
        elif model == RepositoryScript:
            m.filter.return_value.count.return_value = 0
        return m

    mock_db_session.query.side_effect = query_side_effect

    hook_result = {
        "success": True,
        "execution_logs": [],
        "scripts_executed": 1,
        "scripts_failed": 0,
        "using_library": False,
    }

    mock_process = AsyncMock()
    mock_process.returncode = 2
    mock_process.stdout = AsyncMock()
    mock_process.stdout.__aiter__.return_value = iter([])

    with patch(
        "app.services.backup_service.asyncio.create_subprocess_exec",
        return_value=mock_process,
    ):
        with patch(
            "app.services.backup_service.SessionLocal", return_value=mock_db_session
        ):
            with patch(
                "app.services.backup_service.BorgRouter.validate_local_repository_access",
                return_value=None,
            ):
                with patch(
                    "app.services.backup_service.notification_service",
                    _notification_service_mock(),
                ):
                    with patch.object(
                        backup_service_fixture,
                        "_execute_hooks",
                        new=AsyncMock(return_value=hook_result),
                    ) as mock_hooks:
                        await backup_service_fixture.execute_backup(
                            job_id, repo.path, db=mock_db_session
                        )

    post_hook_calls = [
        call
        for call in mock_hooks.await_args_list
        if call.kwargs.get("hook_type") == "post-backup"
    ]
    assert len(post_hook_calls) == 1
    assert post_hook_calls[0].kwargs["backup_result"] == "failure"


@pytest.mark.asyncio
async def test_calculate_source_size_local(backup_service_fixture):
    """Test local directory size calculation"""
    paths = ["/local/path"]

    # Mock du command output
    mock_process = AsyncMock()
    mock_process.returncode = 0
    mock_process.communicate.return_value = (b"1024\t/local/path", b"")

    with patch(
        "app.services.backup_service.asyncio.create_subprocess_exec",
        return_value=mock_process,
    ) as mock_exec:
        # EXECUTE
        size = await backup_service_fixture._calculate_source_size(paths)

        # VERIFY
        assert size == 1024
        args = mock_exec.call_args[0]
        assert args[0] == "du"
        assert "/local/path" in args


@pytest.mark.asyncio
async def test_calculate_source_size_ssh(backup_service_fixture):
    """Test SSH directory size calculation"""
    paths = ["ssh://user@host:22/remote/path"]

    # Mock ssh command output
    mock_process = AsyncMock()
    mock_process.returncode = 0
    mock_process.communicate.return_value = (b"2048", b"")

    with patch(
        "app.services.backup_service.asyncio.create_subprocess_exec",
        return_value=mock_process,
    ) as mock_exec:
        # EXECUTE
        size = await backup_service_fixture._calculate_source_size(paths)

        # VERIFY
        assert size == 2048
        args = mock_exec.call_args[0]
        assert args[0] == "ssh"
        assert "user@host" in args
        assert "du -sb" in args[len(args) - 1]  # Command is last arg


@pytest.mark.asyncio
async def test_calculate_source_size_ssh_uses_key_file_by_target(
    backup_service_fixture,
):
    """Test SSH directory size calculation uses the matching source key."""
    paths = ["ssh://user@host:2222/remote/path"]

    mock_process = AsyncMock()
    mock_process.returncode = 0
    mock_process.communicate.return_value = (b"2048", b"")

    with patch(
        "app.services.backup_service.asyncio.create_subprocess_exec",
        return_value=mock_process,
    ) as mock_exec:
        size = await backup_service_fixture._calculate_source_size(
            paths,
            key_files_by_ssh_target={("user", "host", "2222"): "/tmp/source.key"},
        )

    assert size == 2048
    args = mock_exec.call_args[0]
    assert args[0] == "ssh"
    assert "-i" in args
    assert "/tmp/source.key" in args
    assert "user@host" in args


@pytest.mark.asyncio
async def test_calculate_source_size_ssh_retries_login_relative_du(
    backup_service_fixture,
):
    """Test SSH source size retries the login-relative path for eligible targets."""
    paths = ["ssh://user@host:22/remote/path"]

    first_process = AsyncMock()
    first_process.returncode = 0
    first_process.communicate.return_value = (b"", b"")
    second_process = AsyncMock()
    second_process.returncode = 0
    second_process.communicate.return_value = (b"2048", b"")

    with patch(
        "app.services.backup_service.asyncio.create_subprocess_exec",
        side_effect=[first_process, second_process],
    ) as mock_exec:
        size = await backup_service_fixture._calculate_source_size(
            paths,
            key_files_by_ssh_target={("user", "host", "22"): "/tmp/source.key"},
            login_relative_ssh_targets={("user", "host", "22")},
        )

    assert size == 2048
    first_cmd = mock_exec.call_args_list[0].args
    second_cmd = mock_exec.call_args_list[1].args
    assert first_cmd[-1] == "du -sb /remote/path 2>/dev/null | cut -f1"
    assert second_cmd[-1] == "du -sb remote/path 2>/dev/null | cut -f1"


@pytest.mark.asyncio
async def test_calculate_source_size_ssh_does_not_retry_du_without_login_relative_target(
    backup_service_fixture,
):
    paths = ["ssh://user@host:22/remote/path"]

    process = AsyncMock()
    process.returncode = 0
    process.communicate.return_value = (b"", b"")

    with patch(
        "app.services.backup_service.asyncio.create_subprocess_exec",
        return_value=process,
    ) as mock_exec:
        size = await backup_service_fixture._calculate_source_size(
            paths,
            key_files_by_ssh_target={("user", "host", "22"): "/tmp/source.key"},
            login_relative_ssh_targets=set(),
        )

    assert size == 0
    assert mock_exec.call_count == 1
    assert mock_exec.call_args.args[-1] == "du -sb /remote/path 2>/dev/null | cut -f1"


def test_resolve_source_size_ssh_key_files_matches_each_remote_source(
    backup_service_fixture, mock_db_session
):
    source_a = SSHConnection(
        id=11,
        host="server-a.example",
        username="backup-a",
        port=22,
        ssh_key_id=101,
    )
    source_b = SSHConnection(
        id=12,
        host="server-b.example",
        username="backup-b",
        port=2222,
        ssh_key_id=202,
    )
    ssh_query = MagicMock()
    ssh_query.filter.return_value.first.side_effect = [source_a, source_b]

    def query_side_effect(model):
        if model == SSHConnection:
            return ssh_query
        return MagicMock()

    mock_db_session.query.side_effect = query_side_effect

    with patch(
        "app.services.backup_service.resolve_ssh_key_file_by_id",
        side_effect=["/tmp/source-a.key", "/tmp/source-b.key"],
    ) as resolve_key:
        key_files = backup_service_fixture._resolve_source_size_ssh_key_files(
            mock_db_session,
            [
                "ssh://backup-a@server-a.example:22/home/backup-a/data",
                "/srv/app",
                "ssh://backup-b@server-b.example:2222/var/lib/service",
            ],
        )

    assert key_files == {
        ("backup-a", "server-a.example", "22"): "/tmp/source-a.key",
        ("backup-b", "server-b.example", "2222"): "/tmp/source-b.key",
    }
    assert [call.args[0] for call in resolve_key.call_args_list] == [101, 202]


def test_resolve_source_size_ssh_key_files_reuses_same_key_file(
    backup_service_fixture, mock_db_session
):
    source_a = SSHConnection(
        id=11,
        host="server-a.example",
        username="backup-a",
        port=22,
        ssh_key_id=101,
    )
    source_b = SSHConnection(
        id=12,
        host="server-b.example",
        username="backup-b",
        port=2222,
        ssh_key_id=101,
    )
    ssh_query = MagicMock()
    ssh_query.filter.return_value.first.side_effect = [source_a, source_b]

    def query_side_effect(model):
        if model == SSHConnection:
            return ssh_query
        return MagicMock()

    mock_db_session.query.side_effect = query_side_effect

    with patch(
        "app.services.backup_service.resolve_ssh_key_file_by_id",
        return_value="/tmp/shared-source.key",
    ) as resolve_key:
        key_files = backup_service_fixture._resolve_source_size_ssh_key_files(
            mock_db_session,
            [
                "ssh://backup-a@server-a.example:22/home/backup-a/data",
                "ssh://backup-b@server-b.example:2222/var/lib/service",
            ],
        )

    assert key_files == {
        ("backup-a", "server-a.example", "22"): "/tmp/shared-source.key",
        ("backup-b", "server-b.example", "2222"): "/tmp/shared-source.key",
    }
    resolve_key.assert_called_once_with(101, db=mock_db_session)


def test_resolve_source_size_login_relative_targets_respects_default_path(
    backup_service_fixture, mock_db_session
):
    root_connection = SSHConnection(
        id=11,
        host="server-a.example",
        username="backup-a",
        port=22,
        default_path="/",
    )
    explicit_connection = SSHConnection(
        id=12,
        host="server-b.example",
        username="backup-b",
        port=2222,
        default_path="/srv",
    )
    ssh_query = MagicMock()
    ssh_query.filter.return_value.first.side_effect = [
        root_connection,
        explicit_connection,
        explicit_connection,
    ]

    def query_side_effect(model):
        if model == SSHConnection:
            return ssh_query
        return MagicMock()

    mock_db_session.query.side_effect = query_side_effect

    targets = backup_service_fixture._resolve_source_size_login_relative_targets(
        mock_db_session,
        [
            "ssh://backup-a@server-a.example:22/backups",
            "ssh://backup-b@server-b.example:2222/srv/data",
            "ssh://backup-b@server-b.example:2222/./relative-data",
        ],
    )

    assert targets == {
        ("backup-a", "server-a.example", "22"),
        ("backup-b", "server-b.example", "2222"),
    }


@pytest.mark.asyncio
async def test_calculate_and_update_size_background_passes_source_keys_and_cleans(
    backup_service_fixture, mock_db_session
):
    paths = ["ssh://backup-a@server-a.example:22/home/backup-a/data"]
    key_files = {("backup-a", "server-a.example", "22"): "/tmp/source-a.key"}

    with (
        patch("app.services.backup_service.SessionLocal", return_value=mock_db_session),
        patch.object(
            backup_service_fixture,
            "_resolve_source_size_ssh_key_files",
            return_value=key_files,
        ) as resolve_keys,
        patch.object(
            backup_service_fixture,
            "_resolve_source_size_login_relative_targets",
            return_value={("backup-a", "server-a.example", "22")},
        ) as resolve_login_relative_targets,
        patch.object(
            backup_service_fixture,
            "_calculate_source_size",
            new=AsyncMock(return_value=0),
        ) as calculate_size,
        patch("app.services.backup_service.cleanup_temp_key_file") as cleanup_key,
    ):
        await backup_service_fixture._calculate_and_update_size_background(
            job_id=42,
            source_paths=paths,
            exclude_patterns=None,
        )

    resolve_keys.assert_called_once_with(mock_db_session, paths)
    resolve_login_relative_targets.assert_called_once_with(mock_db_session, paths)
    calculate_size.assert_awaited_once_with(
        paths,
        [],
        key_files_by_ssh_target=key_files,
        login_relative_ssh_targets={("backup-a", "server-a.example", "22")},
    )
    cleanup_key.assert_called_once_with("/tmp/source-a.key")
    mock_db_session.close.assert_called_once()


def _make_skip_query_side_effect(job, repo):
    """Shared DB query mock used by skip-on-failure tests."""

    def query_side_effect(model):
        m = MagicMock()
        if model == BackupJob:
            m.filter.return_value.first.return_value = job
        elif model == Repository:
            m.filter.return_value.first.return_value = repo
        elif model == SystemSettings:
            m.first.return_value = SystemSettings()
        elif model == RepositoryScript:
            m.filter.return_value.count.return_value = 0
        return m

    return query_side_effect


def _make_execute_query_side_effect(job, repo):
    """Shared DB query mock used by execute_backup branch tests."""

    def query_side_effect(model):
        m = MagicMock()
        if model == BackupJob:
            m.filter.return_value.first.return_value = job
        elif model == Repository:
            m.filter.return_value.first.return_value = repo
        elif model == SystemSettings:
            m.first.return_value = SystemSettings()
        elif model == RepositoryScript:
            m.filter.return_value.count.return_value = 0
        return m

    return query_side_effect


@pytest.mark.asyncio
async def test_sync_rclone_after_borg_preserves_existing_borg_warning(
    backup_service_fixture, mock_db_session
):
    repo = Repository(id=7, name="Repo", path="/cache/repositories/7")
    repo.storage = RepositoryStorage(
        repository_id=7,
        backend="rclone",
        rclone_remote_id=3,
        rclone_remote_path="borg-ui/repositories/repo",
        cache_path="/cache/repositories/7",
        sync_policy="after_success",
        sync_status="pending",
    )
    job = BackupJob(
        id=19,
        status="completed_with_warnings",
        error_message=json.dumps(
            {
                "key": "backend.errors.service.backupCompletedWithWarning",
                "params": {"exitCode": 105},
            }
        ),
    )

    with patch(
        "app.services.backup_service.rclone_repository_service.sync_repository",
        new=AsyncMock(
            return_value={
                "sync_status": "failed",
                "last_sync_error": "remote unavailable",
            }
        ),
    ):
        result = await backup_service_fixture._sync_rclone_after_borg(
            mock_db_session, repo, job
        )

    payload = json.loads(job.error_message)
    assert result is False
    assert payload["key"] == "backend.errors.service.backupCompletedWithWarning"
    assert payload["params"]["exitCode"] == 105
    assert payload["params"]["rclone_error"] == "remote unavailable"
    assert job.status == "completed_with_warnings"


@pytest.mark.asyncio
async def test_execute_backup_uses_rclone_sync_failure_for_hooks_and_notifications(
    backup_service_fixture, mock_db_session, tmp_path
):
    job_id = 46
    source_path = tmp_path / "data"
    source_path.mkdir()
    repo = Repository(
        id=1,
        path="/backups/repo",
        source_directories=f'["{source_path}"]',
        compression="lz4",
    )
    job = BackupJob(id=job_id, status="pending")
    mock_db_session.query.side_effect = _make_execute_query_side_effect(job, repo)

    mock_process = AsyncMock()
    mock_process.returncode = 0
    mock_process.stdout = AsyncMock()
    mock_process.stdout.__aiter__.return_value = iter([])

    async def mark_rclone_warning(db, repo_record, backup_job):
        backup_job.status = "completed_with_warnings"
        backup_job.error_message = json.dumps(
            {
                "key": "backend.errors.rclone.syncFailedAfterBackup",
                "params": {"error": "remote unavailable"},
            }
        )
        return False

    hook_result = {
        "success": True,
        "execution_logs": [],
        "scripts_executed": 0,
        "scripts_failed": 0,
        "using_library": False,
    }
    execute_hooks = AsyncMock(return_value=hook_result)
    notifications = _notification_service_mock()

    with (
        patch("app.services.backup_service.SessionLocal", return_value=mock_db_session),
        patch(
            "app.services.backup_service.BorgRouter.validate_local_repository_access",
            return_value=None,
        ),
        patch.object(backup_service_fixture, "_execute_hooks", execute_hooks),
        patch.object(
            backup_service_fixture,
            "_prepare_source_paths",
            new=AsyncMock(return_value=([str(source_path)], [])),
        ),
        patch.object(
            backup_service_fixture,
            "_calculate_and_update_size_background",
            new=AsyncMock(),
        ),
        patch.object(backup_service_fixture, "_update_archive_stats", new=AsyncMock()),
        patch.object(
            backup_service_fixture, "_update_repository_stats", new=AsyncMock()
        ),
        patch.object(
            backup_service_fixture,
            "_sync_rclone_after_borg",
            new=AsyncMock(side_effect=mark_rclone_warning),
        ),
        patch(
            "app.services.backup_service.asyncio.create_subprocess_exec",
            return_value=mock_process,
        ),
        patch("app.services.backup_service.notification_service", notifications),
        patch("app.services.backup_service.mqtt_service") as mqtt,
    ):
        mqtt.sync_state_with_db = Mock()
        await backup_service_fixture.execute_backup(
            job_id, repo.path, db=mock_db_session
        )

    post_hook_calls = [
        call
        for call in execute_hooks.await_args_list
        if call.kwargs.get("hook_type") == "post-backup"
    ]
    assert post_hook_calls[0].kwargs["backup_result"] == "warning"
    assert job.status == "completed_with_warnings"
    notifications.send_backup_warning.assert_awaited_once()
    notifications.send_backup_success.assert_not_awaited()


@pytest.mark.asyncio
async def test_execute_backup_post_hook_failure_sends_single_failure_notification(
    backup_service_fixture, mock_db_session
):
    job_id = 47
    repo = Repository(
        id=1,
        path="/backups/repo",
        source_directories='["/data"]',
        compression="lz4",
    )
    job = BackupJob(id=job_id, status="pending")
    mock_db_session.query.side_effect = _make_execute_query_side_effect(job, repo)

    mock_process = AsyncMock()
    mock_process.returncode = 0
    mock_process.stdout = AsyncMock()
    mock_process.stdout.__aiter__.return_value = iter([])

    pre_hook_result = {
        "success": True,
        "execution_logs": [],
        "scripts_executed": 0,
        "scripts_failed": 0,
        "using_library": False,
    }
    post_hook_result = {
        "success": False,
        "execution_logs": ["post hook failed"],
        "scripts_executed": 1,
        "scripts_failed": 1,
        "using_library": False,
    }
    execute_hooks = AsyncMock(side_effect=[pre_hook_result, post_hook_result])
    notifications = _notification_service_mock()

    with (
        patch("app.services.backup_service.SessionLocal", return_value=mock_db_session),
        patch(
            "app.services.backup_service.BorgRouter.validate_local_repository_access",
            return_value=None,
        ),
        patch.object(backup_service_fixture, "_execute_hooks", execute_hooks),
        patch.object(
            backup_service_fixture,
            "_prepare_source_paths",
            new=AsyncMock(return_value=(["/data"], [])),
        ),
        patch.object(
            backup_service_fixture,
            "_calculate_and_update_size_background",
            new=AsyncMock(),
        ),
        patch.object(backup_service_fixture, "_update_archive_stats", new=AsyncMock()),
        patch.object(
            backup_service_fixture, "_update_repository_stats", new=AsyncMock()
        ),
        patch(
            "app.services.backup_service.asyncio.create_subprocess_exec",
            return_value=mock_process,
        ),
        patch("app.services.backup_service.notification_service", notifications),
        patch("app.services.backup_service.mqtt_service") as mqtt,
    ):
        mqtt.sync_state_with_db = Mock()
        await backup_service_fixture.execute_backup(
            job_id, repo.path, db=mock_db_session
        )

    assert job.status == "failed"
    notifications.send_backup_failure.assert_awaited_once()


@pytest.mark.asyncio
async def test_pre_backup_inline_script_failure_skips_when_flag_set(
    backup_service_fixture, mock_db_session
):
    """
    When skip_on_hook_failure=True and an inline pre-backup script fails,
    the job must be marked 'skipped' – not 'failed' – and borg must not run.
    """
    job_id = 42
    repo = Repository(
        id=1,
        path="/backups/repo",
        source_directories='["/data"]',
        pre_backup_script="exit 1",
        skip_on_hook_failure=True,
    )
    job = BackupJob(id=job_id, status="pending")
    mock_db_session.query.side_effect = _make_skip_query_side_effect(job, repo)

    inline_failure = {
        "success": False,
        "execution_logs": ["pre-backup script exited with code 1"],
        "scripts_executed": 1,
        "scripts_failed": 1,
        "using_library": False,
    }

    with patch.object(
        backup_service_fixture, "_execute_hooks", return_value=inline_failure
    ):
        with patch(
            "app.services.backup_service.SessionLocal", return_value=mock_db_session
        ):
            with patch(
                "app.services.backup_service.BorgRouter.validate_local_repository_access",
                return_value=None,
            ):
                with patch(
                    "app.services.backup_service.notification_service",
                    _notification_service_mock(),
                ):
                    with patch(
                        "app.services.backup_service.asyncio.create_subprocess_exec"
                    ) as mock_exec:
                        await backup_service_fixture.execute_backup(
                            job_id, repo.path, db=mock_db_session
                        )

    assert job.status == "skipped", f"expected 'skipped', got '{job.status}'"
    assert "Skipped by pre-backup script" in job.error_message
    # borg create must never be called when the backup is skipped
    borg_calls = [c for c in mock_exec.call_args_list if c[0] and c[0][0] == "borg"]
    assert borg_calls == [], "borg must not run when backup is skipped"


@pytest.mark.asyncio
async def test_pre_backup_inline_script_failure_fails_job_when_skip_flag_off(
    backup_service_fixture, mock_db_session
):
    """
    When skip_on_hook_failure=False (the default) and a pre-backup script fails,
    the job must be marked 'failed', not silently skipped.
    """
    job_id = 43
    repo = Repository(
        id=1,
        path="/backups/repo",
        source_directories='["/data"]',
        pre_backup_script="exit 1",
        skip_on_hook_failure=False,
        continue_on_hook_failure=False,
    )
    job = BackupJob(id=job_id, status="pending")
    mock_db_session.query.side_effect = _make_skip_query_side_effect(job, repo)

    inline_failure = {
        "success": False,
        "execution_logs": ["pre-backup script exited with code 1"],
        "scripts_executed": 1,
        "scripts_failed": 1,
        "using_library": False,
    }

    with patch.object(
        backup_service_fixture, "_execute_hooks", return_value=inline_failure
    ):
        with patch(
            "app.services.backup_service.SessionLocal", return_value=mock_db_session
        ):
            with patch(
                "app.services.backup_service.BorgRouter.validate_local_repository_access",
                return_value=None,
            ):
                with patch(
                    "app.services.backup_service.notification_service",
                    _notification_service_mock(),
                ):
                    await backup_service_fixture.execute_backup(
                        job_id, repo.path, db=mock_db_session
                    )

    assert job.status == "failed", f"expected 'failed', got '{job.status}'"


@pytest.mark.asyncio
async def test_pre_backup_library_should_skip_signal_skips_job(
    backup_service_fixture, mock_db_session
):
    """
    When a script-library hook returns should_skip=True (e.g. a maintenance-guard
    script that intentionally declines the run), the job must be marked 'skipped'
    with the script name included in the error message.
    """
    job_id = 44
    repo = Repository(
        id=1,
        path="/backups/repo",
        source_directories='["/data"]',
    )
    job = BackupJob(id=job_id, status="pending")
    mock_db_session.query.side_effect = _make_skip_query_side_effect(job, repo)

    library_skip = {
        "success": False,
        "should_skip": True,
        "skip_script_name": "maintenance-guard",
        "execution_logs": ["maintenance window active – skipping backup"],
        "scripts_executed": 1,
        "scripts_failed": 1,
        "using_library": True,
    }

    with patch.object(
        backup_service_fixture, "_execute_hooks", return_value=library_skip
    ):
        with patch(
            "app.services.backup_service.SessionLocal", return_value=mock_db_session
        ):
            with patch(
                "app.services.backup_service.BorgRouter.validate_local_repository_access",
                return_value=None,
            ):
                with patch(
                    "app.services.backup_service.notification_service",
                    _notification_service_mock(),
                ):
                    with patch(
                        "app.services.backup_service.asyncio.create_subprocess_exec"
                    ) as mock_exec:
                        await backup_service_fixture.execute_backup(
                            job_id, repo.path, db=mock_db_session
                        )

    assert job.status == "skipped", f"expected 'skipped', got '{job.status}'"
    assert "maintenance-guard" in job.error_message
    borg_calls = [c for c in mock_exec.call_args_list if c[0] and c[0][0] == "borg"]
    assert borg_calls == [], (
        "borg must not run when backup is skipped by library script"
    )


@pytest.mark.asyncio
async def test_log_rotation(backup_service_fixture, mock_db_session):
    """Test log rotation calls log_manager"""
    # Setup Data
    mock_db_session.query.return_value.first.return_value = SystemSettings(
        log_retention_days=7, log_max_total_size_mb=100
    )

    mock_result = {
        "success": True,
        "total_deleted_count": 5,
        "total_deleted_size_mb": 10,
        "age_cleanup": {"deleted_count": 2},
        "size_cleanup": {"deleted_count": 3},
    }

    with patch(
        "app.services.log_manager.log_manager.cleanup_logs_combined",
        return_value=mock_result,
    ) as mock_cleanup:
        # EXECUTE
        backup_service_fixture.rotate_logs(db=mock_db_session)

        # VERIFY
        mock_cleanup.assert_called_once()
        kwargs = mock_cleanup.call_args.kwargs
        assert kwargs["max_age_days"] == 7
        assert kwargs["max_total_size_mb"] == 100


@pytest.mark.asyncio
async def test_execute_backup_delegates_remote_ssh_job(
    backup_service_fixture, mock_db_session
):
    job_id = 50
    repo = Repository(
        id=1,
        path="/backups/repo",
        source_directories='["/remote/data"]',
        exclude_patterns='["*.tmp"]',
        compression="lz4",
    )
    job = BackupJob(
        id=job_id,
        status="pending",
        execution_mode="remote_ssh",
        source_ssh_connection_id=77,
    )
    mock_db_session.query.side_effect = _make_execute_query_side_effect(job, repo)

    with patch(
        "app.services.remote_backup_service.remote_backup_service.execute_remote_backup",
        new=AsyncMock(),
    ) as mock_remote_execute:
        await backup_service_fixture.execute_backup(
            job_id, repo.path, db=mock_db_session
        )

    mock_remote_execute.assert_awaited_once()
    assert job.status == "pending"


@pytest.mark.asyncio
async def test_execute_backup_resolves_grouped_source_locations(
    backup_service_fixture, mock_db_session, tmp_path
):
    job_id = 501
    local_source = tmp_path / "srv-app"
    local_source.mkdir()
    repo = Repository(
        id=1,
        path="/backups/repo",
        source_directories='["/legacy"]',
        compression="lz4",
        mode="full",
    )
    job = BackupJob(id=job_id, status="pending")
    source_a = SSHConnection(
        id=11,
        host="server-a.example",
        username="backup-a",
        port=22,
        default_path="/home/backup-a",
        status="connected",
    )
    source_b = SSHConnection(
        id=12,
        host="server-b.example",
        username="backup-b",
        port=2222,
        default_path="/",
        status="connected",
    )
    ssh_connection_results = iter([source_a, source_b])
    source_locations = [
        {
            "source_type": "local",
            "source_ssh_connection_id": None,
            "paths": [str(local_source)],
        },
        {
            "source_type": "remote",
            "source_ssh_connection_id": source_a.id,
            "paths": ["data"],
        },
        {
            "source_type": "remote",
            "source_ssh_connection_id": source_b.id,
            "paths": ["/var/lib/service"],
        },
    ]

    def query_side_effect(model):
        m = MagicMock()
        if model == BackupJob:
            m.filter.return_value.first.return_value = job
        elif model == Repository:
            m.filter.return_value.first.return_value = repo
        elif model == SystemSettings:
            m.first.return_value = SystemSettings()
        elif model == RepositoryScript:
            m.filter.return_value.count.return_value = 0
        elif model == SSHConnection:
            m.filter.return_value.first.side_effect = lambda: next(
                ssh_connection_results
            )
        return m

    mock_db_session.query.side_effect = query_side_effect
    mock_process = AsyncMock()
    mock_process.returncode = 0
    mock_process.stdout = AsyncMock()
    mock_process.stdout.__aiter__.return_value = iter([])

    with (
        patch("app.services.backup_service.SessionLocal", return_value=mock_db_session),
        patch(
            "app.services.backup_service.BorgRouter.validate_local_repository_access",
            return_value=None,
        ),
        patch.object(
            backup_service_fixture,
            "_execute_hooks",
            return_value={
                "success": True,
                "execution_logs": [],
                "scripts_executed": 0,
                "scripts_failed": 0,
                "using_library": False,
            },
        ),
        patch.object(
            backup_service_fixture,
            "_prepare_source_paths",
            new=AsyncMock(
                return_value=(
                    [str(local_source), "data", "var/lib/service"],
                    [
                        ("/tmp/sshfs-a", "data"),
                        ("/tmp/sshfs-b", "var/lib/service"),
                    ],
                )
            ),
        ) as prepare_source_paths,
        patch(
            "app.services.backup_service.asyncio.create_subprocess_exec",
            return_value=mock_process,
        ),
        patch(
            "app.services.backup_service.notification_service",
            _notification_service_mock(),
        ),
        patch("app.services.backup_service.mqtt_service") as mqtt,
    ):
        mqtt.sync_state_with_db = Mock()
        await backup_service_fixture.execute_backup(
            job_id,
            repo.path,
            db=mock_db_session,
            source_directories=[str(local_source), "data", "/var/lib/service"],
            source_locations=source_locations,
        )

    prepare_source_paths.assert_awaited_once_with(
        [
            str(local_source),
            "ssh://backup-a@server-a.example:22/home/backup-a/data",
            "ssh://backup-b@server-b.example:2222/var/lib/service",
        ],
        job_id,
        source_connection_id=None,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "source_directories",
    [
        "[]",
        "not-json",
    ],
)
async def test_execute_backup_rejects_missing_or_invalid_source_directories(
    backup_service_fixture, mock_db_session, source_directories
):
    job_id = 51
    repo = Repository(
        id=1,
        path="/backups/repo",
        source_directories=source_directories,
        compression="lz4",
    )
    job = BackupJob(id=job_id, status="pending")
    mock_db_session.query.side_effect = _make_execute_query_side_effect(job, repo)

    notifications = MagicMock()
    notifications.send_backup_failure = AsyncMock()
    notifications.send_backup_start = AsyncMock()
    notifications.send_backup_success = AsyncMock()
    notifications.send_backup_warning = AsyncMock()

    with (
        patch("app.services.backup_service.notification_service", notifications),
        patch("app.services.backup_service.mqtt_service") as mqtt,
    ):
        mqtt.sync_state_with_db = Mock()
        await backup_service_fixture.execute_backup(
            job_id, repo.path, db=mock_db_session
        )

    assert job.status == "failed"
    assert job.error_message == json.dumps({"key": "backend.errors.borg.unknownError"})


@pytest.mark.asyncio
async def test_execute_backup_rejects_observe_mode(
    backup_service_fixture, mock_db_session
):
    job_id = 52
    repo = Repository(
        id=1,
        path="/backups/repo",
        source_directories='["/data"]',
        mode="observe",
        compression="lz4",
    )
    job = BackupJob(id=job_id, status="pending")
    mock_db_session.query.side_effect = _make_execute_query_side_effect(job, repo)

    with (
        patch("app.services.backup_service.notification_service"),
        patch("app.services.backup_service.mqtt_service") as mqtt,
    ):
        mqtt.sync_state_with_db = Mock()
        await backup_service_fixture.execute_backup(
            job_id, repo.path, db=mock_db_session
        )

    assert job.status == "failed"
    assert job.error_message == json.dumps({"key": "backend.errors.borg.unknownError"})
