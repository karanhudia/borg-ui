
import pytest
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock, call
from app.services.backup_service import BackupService, backup_service
from app.database.models import BackupJob, Repository, SystemSettings, RepositoryScript

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
        mock_conf.script_timeout = 60 # Fix for size calculation
        mock_conf.borg_info_timeout = 60
        mock_conf.borg_list_timeout = 60
        mock_conf.source_size_timeout = 120
        
        with patch("app.services.backup_service.Path") as mock_path:
             # Mock filesystem paths
            mock_path.return_value.exists.return_value = True
            mock_path.return_value.mkdir.return_value = None
            
            service = BackupService()
            yield service

@pytest.mark.asyncio
async def test_execute_backup_command(backup_service_fixture, mock_db_session):
    """Test 'borg create' command construction"""
    # Setup Data
    job_id = 999
    repo = Repository(
        id=1, 
        path="/backups/repo", 
        compression="zstd,3",
        source_directories='["/home/user/data"]',
        exclude_patterns='["*.tmp"]',
        passphrase="secret",
        mode="full"
    )
    job = BackupJob(id=job_id, status="pending")

    # Mock DB query
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
    mock_process.stdout.__aiter__.return_value = iter([b'{"type": "archive_progress", "original_size": 100}'])
    
    with patch("app.services.backup_service.asyncio.create_subprocess_exec", return_value=mock_process) as mock_exec:
        with patch("app.services.backup_service.SessionLocal", return_value=mock_db_session):
            with patch("app.services.backup_service.notification_service") as mock_notif:
                # Patch hooks to avoid complexity in this specific test
                with patch.object(backup_service_fixture, '_execute_hooks', return_value={"success": True, "execution_logs": [], "scripts_executed": 0, "scripts_failed": 0, "using_library": False}):
                     # EXECUTE
                    await backup_service_fixture.execute_backup(job_id, repo.path, db=mock_db_session)

                    # VERIFY
                    # Verify command arguments - search for the 'create' command in all calls
                    create_call_args = None
                    for call_args in mock_exec.call_args_list:
                        args = call_args[0]
                        if len(args) > 1 and args[0] == "borg" and args[1] == "create":
                            create_call_args = args
                            break
                    
                    assert create_call_args is not None, "borg create command was not executed"
                    
                    assert "--compression" in create_call_args
                    assert "zstd,3" in create_call_args
                    assert "--exclude" in create_call_args
                    assert "*.tmp" in create_call_args
                    assert "/home/user/data" in create_call_args # Source path
                    
                    # Verify content of the archive argument
                    archive_arg = [a for a in create_call_args if "::" in a][0]
                    assert archive_arg.startswith("/backups/repo::manual-backup-")

@pytest.mark.asyncio
async def test_execute_backup_hooks(backup_service_fixture, mock_db_session):
    """Test pre/post backup hook execution"""
    # Setup Data
    job_id = 999
    repo = Repository(
        id=1, 
        path="/backups/repo",
        source_directories='["/data"]',
        pre_backup_script="echo pre",
        post_backup_script="echo post"
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
    mock_executor_result = {"success": True, "logs": ["executed"], "stdout": "", "stderr": "", "exit_code": 0}
    
    with patch("app.services.backup_service.ScriptLibraryExecutor") as MockExecutor:
        # Properly mock async method
        instance = MockExecutor.return_value
        instance.execute_inline_script = AsyncMock(return_value=mock_executor_result)
        
        # Mock subprocess for actual backup - empty iterator to avoid errors
        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.stdout = AsyncMock()
        mock_process.stdout.__aiter__.return_value = iter([])
        
        with patch("app.services.backup_service.asyncio.create_subprocess_exec", return_value=mock_process):
             with patch("app.services.backup_service.SessionLocal", return_value=mock_db_session):
                 with patch("app.services.backup_service.notification_service"):
                     # EXECUTE
                    await backup_service_fixture.execute_backup(job_id, repo.path, db=mock_db_session)

                    # VERIFY Hooks called
                    # Should be called once for pre-backup and once for post-backup
                    assert instance.execute_inline_script.call_count == 2
                    
                    # Check first call was pre-backup
                    call1 = instance.execute_inline_script.call_args_list[0]
                    assert call1.kwargs['script_type'] == "pre-backup"
                    
                    # Check second call was post-backup
                    call2 = instance.execute_inline_script.call_args_list[1]
                    assert call2.kwargs['script_type'] == "post-backup"

@pytest.mark.asyncio
async def test_calculate_source_size_local(backup_service_fixture):
    """Test local directory size calculation"""
    paths = ["/local/path"]
    
    # Mock du command output
    mock_process = AsyncMock()
    mock_process.returncode = 0
    mock_process.communicate.return_value = (b"1024\t/local/path", b"")
    
    with patch("app.services.backup_service.asyncio.create_subprocess_exec", return_value=mock_process) as mock_exec:
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
    
    with patch("app.services.backup_service.asyncio.create_subprocess_exec", return_value=mock_process) as mock_exec:
        # EXECUTE
        size = await backup_service_fixture._calculate_source_size(paths)
        
        # VERIFY
        assert size == 2048
        args = mock_exec.call_args[0]
        assert args[0] == "ssh"
        assert "user@host" in args
        assert "du -sb" in args[len(args)-1] # Command is last arg

@pytest.mark.asyncio
async def test_log_rotation(backup_service_fixture, mock_db_session):
    """Test log rotation calls log_manager"""
    # Setup Data
    mock_db_session.query.return_value.first.return_value = SystemSettings(
        log_retention_days=7,
        log_max_total_size_mb=100
    )
    
    mock_result = {
        "success": True, 
        "total_deleted_count": 5, 
        "total_deleted_size_mb": 10,
        "age_cleanup": {"deleted_count": 2},
        "size_cleanup": {"deleted_count": 3}
    }
    
    with patch("app.services.log_manager.log_manager.cleanup_logs_combined", return_value=mock_result) as mock_cleanup:
        # EXECUTE
        backup_service_fixture.rotate_logs(db=mock_db_session)
        
        # VERIFY
        mock_cleanup.assert_called_once()
        kwargs = mock_cleanup.call_args.kwargs
        assert kwargs['max_age_days'] == 7
        assert kwargs['max_total_size_mb'] == 100
