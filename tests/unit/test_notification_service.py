
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from app.services.notification_service import notification_service
from app.database.models import Repository, NotificationSettings

@pytest.fixture
def mock_apprise():
    with patch("app.services.notification_service.apprise.Apprise") as mock:
        yield mock

@pytest.fixture
def mock_repository(test_db):
    repo = Repository(name="Test Repo", path="/tmp/test-repo")
    test_db.add(repo)
    test_db.commit()
    test_db.refresh(repo)
    return repo

@pytest.fixture
def email_notification_setting(test_db, mock_repository):
    setting = NotificationSettings(
        name="Email Alert",
        service_url="mailto://user:pass@smtp.example.com",
        enabled=True,
        notify_on_backup_success=True,
        notify_on_backup_failure=True,
        title_prefix="[Borg]",
        monitor_all_repositories=False  # Important for filtering tests
    )
    setting.repositories.append(mock_repository)
    test_db.add(setting)
    test_db.commit()
    test_db.refresh(setting)
    return setting

@pytest.fixture
def discord_notification_setting(test_db, mock_repository):
    setting = NotificationSettings(
        name="Discord Alert",
        service_url="discord://webhook_id/token",
        enabled=True,
        notify_on_backup_success=True,
        notify_on_backup_failure=True
    )
    setting.repositories.append(mock_repository)
    test_db.add(setting)
    test_db.commit()
    test_db.refresh(setting)
    return setting

@pytest.mark.asyncio
async def test_send_backup_success_email(test_db, mock_apprise, mock_repository, email_notification_setting):
    """Test sending success notification via Email (HTML format)"""
    # Setup mock
    apprise_instance = mock_apprise.return_value
    apprise_instance.add.return_value = True
    apprise_instance.notify.return_value = True

    # Action
    stats = {"original_size": 1024 * 1024, "compressed_size": 512 * 1024, "deduplicated_size": 100}
    await notification_service.send_backup_success(
        test_db, 
        mock_repository.name, 
        "archive-2024", 
        stats=stats
    )

    # Assert
    assert apprise_instance.add.call_count == 1
    # Verify mock was called with HTML format
    call_args = apprise_instance.notify.call_args[1]
    assert call_args['title'] == "[Borg] ✅ Backup Successful"
    assert "1.00 MB" in call_args['body']  # Formatted original size
    assert "512.00 KB" in call_args['body'] # Formatted compressed size
    assert "<html>" in call_args['body']
    
@pytest.mark.asyncio
async def test_send_backup_failure_discord(test_db, mock_apprise, mock_repository, discord_notification_setting):
    """Test sending failure notification via Discord (Markdown format)"""
    # Setup mock
    apprise_instance = mock_apprise.return_value
    apprise_instance.add.return_value = True
    apprise_instance.notify.return_value = True

    # Action
    job_id = 123
    error_msg = "Connection timed out"
    await notification_service.send_backup_failure(
        test_db, 
        mock_repository.name, 
        error_msg,
        job_id=job_id
    )

    # Assert
    assert apprise_instance.add.call_count == 1
    # Verify mock was called with Markdown format (implicit for non-email)
    call_args = apprise_instance.notify.call_args[1]
    assert call_args['title'] == "❌ Backup Failed"
    assert error_msg in call_args['body']
    assert str(job_id) in call_args['body']
    assert "```" in call_args['body'] # Markdown code block

@pytest.mark.asyncio
async def test_repo_filtering(test_db, mock_apprise, mock_repository, email_notification_setting):
    """Test that notifications are NOT sent for excluded repositories"""
    # Setup mock
    apprise_instance = mock_apprise.return_value
    
    # Create another repo NOT linked to the setting
    other_repo = Repository(name="Other Repo", path="/tmp/other")
    test_db.add(other_repo)
    test_db.commit()

    # Action: Trigge notification for the OTHER repo
    await notification_service.send_backup_success(
        test_db, 
        other_repo.name, 
        "archive-other"
    )

    # Assert: Should NOT call notify because the setting filters to "Test Repo" only
    apprise_instance.notify.assert_not_called()

@pytest.mark.asyncio
async def test_global_repo_setting(test_db, mock_apprise, mock_repository, email_notification_setting):
    """Test that monitor_all_repositories=True ignores filters"""
    # Setup mock
    apprise_instance = mock_apprise.return_value
    apprise_instance.add.return_value = True
    apprise_instance.notify.return_value = True
    
    # Enable global monitoring
    email_notification_setting.monitor_all_repositories = True
    email_notification_setting.repositories = [] # Clear specific list
    test_db.commit()
    
    # Create another repo
    other_repo = Repository(name="New Repo", path="/tmp/new")
    test_db.add(other_repo)
    test_db.commit()

    # Action
    await notification_service.send_backup_success(
        test_db, 
        other_repo.name, 
        "archive-new"
    )

    # Assert: Should call notify because monitor_all_repositories is True
    assert apprise_instance.notify.call_count == 1
