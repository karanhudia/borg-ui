
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
    assert call_args['title'] == "[Borg] [SUCCESS] Backup Successful"
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
    assert call_args['title'] == "[FAILED] Backup Failed"
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


# ============================================================================
# Tests for notification enhancements (job name + JSON data)
# ============================================================================

from app.services.notification_service import (
    _is_webhook_service,
    _is_email_service,
    _should_include_json,
    _build_json_data,
    _append_json_to_body,
    _is_json_webhook,
    _sanitize_ssh_url
)
from datetime import datetime
import json as json_module


class TestHelperFunctions:
    """Tests for notification service helper functions"""

    def test_is_email_service(self):
        """Test email service detection"""
        assert _is_email_service("mailto://user:pass@smtp.gmail.com")
        assert _is_email_service("mailtos://user:pass@smtp.gmail.com")
        assert _is_email_service("smtp://smtp.example.com")
        assert _is_email_service("smtps://smtp.example.com")
        assert not _is_email_service("slack://token/channel")
        assert not _is_email_service("discord://webhook")
        assert not _is_email_service("https://webhook.site/abc123")

    def test_is_webhook_service(self):
        """Test webhook service detection"""
        assert _is_webhook_service("http://webhook.site/abc123")
        assert _is_webhook_service("https://webhook.site/abc123")
        assert _is_webhook_service("json://webhook.site/abc123")
        assert _is_webhook_service("jsons://webhook.site/abc123")
        assert _is_webhook_service("form://webhook.site/abc123")
        assert not _is_webhook_service("mailto://user@example.com")
        assert not _is_webhook_service("slack://token")
        assert not _is_webhook_service("discord://webhook")

    def test_should_include_json_for_json_webhooks(self, test_db):
        """Test JSON inclusion for json:// and jsons:// webhooks"""
        setting_jsons = NotificationSettings(
            name="Test",
            service_url="jsons://webhook.site/abc123",
            enabled=True
        )
        assert _should_include_json(setting_jsons) is True

        setting_json = NotificationSettings(
            name="Test",
            service_url="json://myserver.com/webhook",
            enabled=True
        )
        assert _should_include_json(setting_json) is True

    def test_should_not_include_json_for_other_services(self, test_db):
        """Test JSON exclusion for non-JSON webhook services"""
        setting_slack = NotificationSettings(
            name="Test",
            service_url="slack://token",
            enabled=True
        )
        assert _should_include_json(setting_slack) is False

        setting_email = NotificationSettings(
            name="Test",
            service_url="mailto://user@example.com",
            enabled=True
        )
        assert _should_include_json(setting_email) is False

    def test_build_json_data(self):
        """Test JSON data building with pretty-print (default)"""
        data = {
            "repository_name": "my-repo",
            "archive_name": "backup-2024-01-30",
            "stats": {"original_size": 1024, "compressed_size": 512}
        }

        result = _build_json_data("backup_success", data)
        parsed = json_module.loads(result)

        assert parsed["event_type"] == "backup_success"
        assert "timestamp" in parsed
        assert parsed["repository_name"] == "my-repo"
        assert parsed["archive_name"] == "backup-2024-01-30"
        assert parsed["stats"]["original_size"] == 1024

        # Default should be pretty-printed with newlines
        assert '\n' in result

    def test_build_json_data_compact(self):
        """Test JSON data building with compact format"""
        data = {
            "repository_name": "my-repo",
            "archive_name": "backup-2024-01-30"
        }

        result = _build_json_data("backup_success", data, compact=True)
        parsed = json_module.loads(result)

        assert parsed["event_type"] == "backup_success"
        assert "timestamp" in parsed
        assert parsed["repository_name"] == "my-repo"

        # Compact format should have no newlines or extra spaces
        assert '\n' not in result
        assert '  ' not in result  # No double spaces from indentation

    def test_append_json_to_html_body(self):
        """Test JSON appending to HTML body"""
        # Use the actual structure that _create_html_email generates
        html_body = '''<html><body><div>Test content</div>
</body>
</html>'''
        json_data = '{"event": "test", "data": "value"}'

        result = _append_json_to_body(html_body, json_data, is_html=True, service_url='mailto://user@example.com')

        assert '<details>' in result
        assert '<summary' in result
        assert 'JSON Data' in result
        assert json_data in result
        assert '<pre' in result

    def test_append_json_to_markdown_body(self):
        """Test JSON appending to Markdown body"""
        markdown_body = '**Title**\n\nSome content here'
        json_data = '{"event": "test", "data": "value"}'

        result = _append_json_to_body(markdown_body, json_data, is_html=False, service_url='slack://token/channel')

        assert '**JSON Data' in result
        assert '```json' in result
        assert json_data in result
        assert '```' in result

    def test_is_json_webhook(self):
        """Test JSON webhook detection"""
        assert _is_json_webhook("json://webhook.site/abc123")
        assert _is_json_webhook("jsons://webhook.site/abc123")
        assert _is_json_webhook("JSON://WEBHOOK.SITE/ABC")  # Case insensitive
        assert _is_json_webhook("JSONS://example.com")
        assert not _is_json_webhook("https://webhook.site/abc123")
        assert not _is_json_webhook("slack://token/channel")
        assert not _is_json_webhook("mailto://user@example.com")

    def test_append_json_for_json_webhook(self):
        """Test that JSON webhooks receive pure JSON string"""
        body = "Some notification body with details"
        json_data = '{"event": "test", "status": "success", "data": {"key": "value"}}'

        # Test with jsons:// webhook (secure)
        result = _append_json_to_body(body, json_data, is_html=False, service_url='jsons://webhook.site/abc123')
        assert result == json_data
        assert '```json' not in result
        assert '**JSON Data' not in result

        # Test with json:// webhook (insecure)
        result = _append_json_to_body(body, json_data, is_html=False, service_url='json://myserver.com/webhook')
        assert result == json_data
        assert '```json' not in result

        # Test with HTML format (should still return pure JSON for json webhooks)
        result = _append_json_to_body(body, json_data, is_html=True, service_url='jsons://webhook.site/abc123')
        assert result == json_data
        assert '<details>' not in result
        assert '<pre' not in result

    def test_non_json_webhooks_still_get_formatted_json(self):
        """Test that non-JSON webhooks still get markdown/HTML formatted JSON"""
        body = "Some notification body"
        json_data = '{"event": "test"}'

        # Test https:// webhook - should get markdown formatting
        result = _append_json_to_body(body, json_data, is_html=False, service_url='https://webhook.site/abc123')
        assert result != json_data
        assert '```json' in result
        assert '**JSON Data' in result

        # Test form:// webhook - should get markdown formatting
        result = _append_json_to_body(body, json_data, is_html=False, service_url='form://webhook.site/abc123')
        assert result != json_data
        assert '```json' in result

    def test_sanitize_ssh_url_removes_username(self):
        """Test that SSH URL sanitization removes username to prevent @ mentions"""
        # SSH URL with username
        url = "ssh://u331525-sub1@u331525-sub1.your-storagebox.de:23/home/BorgTestRepoKaran"
        result = _sanitize_ssh_url(url)
        assert result == "ssh://u331525-sub1.your-storagebox.de:23/home/BorgTestRepoKaran"
        assert "@" not in result

        # Another SSH URL
        url = "ssh://user@example.com/path/to/repo"
        result = _sanitize_ssh_url(url)
        assert result == "ssh://example.com/path/to/repo"
        assert "@" not in result

    def test_sanitize_ssh_url_preserves_non_ssh_urls(self):
        """Test that non-SSH URLs are unchanged by sanitization"""
        # Local path
        url = "/local/path/to/repo"
        result = _sanitize_ssh_url(url)
        assert result == "/local/path/to/repo"

        # File URL
        url = "file:///local/path"
        result = _sanitize_ssh_url(url)
        assert result == "file:///local/path"

        # HTTP URL (should not be affected)
        url = "http://example.com/path"
        result = _sanitize_ssh_url(url)
        assert result == "http://example.com/path"

    def test_sanitize_ssh_url_handles_edge_cases(self):
        """Test edge cases for SSH URL sanitization"""
        # URL without username (already clean)
        url = "ssh://host.com:22/path"
        result = _sanitize_ssh_url(url)
        assert result == "ssh://host.com:22/path"

        # SFTP URL with username
        url = "sftp://user@host.com/path"
        result = _sanitize_ssh_url(url)
        assert result == "sftp://host.com/path"

        # Empty string
        url = ""
        result = _sanitize_ssh_url(url)
        assert result == ""


@pytest.mark.asyncio
async def test_job_name_in_title_when_enabled(test_db, mock_apprise, mock_repository):
    """Test that job name appears in title when enabled"""
    # Setup notification setting with job name enabled
    setting = NotificationSettings(
        name="Slack Alert",
        service_url="slack://token/channel",
        enabled=True,
        notify_on_backup_success=True,
        include_job_name_in_title=True,
        monitor_all_repositories=True
    )
    test_db.add(setting)
    test_db.commit()

    # Setup mock
    apprise_instance = mock_apprise.return_value
    apprise_instance.add.return_value = True
    apprise_instance.notify.return_value = True

    # Action
    await notification_service.send_backup_success(
        test_db,
        mock_repository.name,
        "archive-2024",
        stats=None,
        completion_time=None,
        job_name="Daily Backup"
    )

    # Assert
    call_args = apprise_instance.notify.call_args[1]
    assert call_args['title'] == "[SUCCESS] Backup Successful - Daily Backup"


@pytest.mark.asyncio
async def test_job_name_not_in_title_when_disabled(test_db, mock_apprise, mock_repository):
    """Test that job name does NOT appear in title when disabled"""
    # Setup notification setting with job name disabled
    setting = NotificationSettings(
        name="Slack Alert",
        service_url="slack://token/channel",
        enabled=True,
        notify_on_backup_success=True,
        include_job_name_in_title=False,
        monitor_all_repositories=True
    )
    test_db.add(setting)
    test_db.commit()

    # Setup mock
    apprise_instance = mock_apprise.return_value
    apprise_instance.add.return_value = True
    apprise_instance.notify.return_value = True

    # Action
    await notification_service.send_backup_success(
        test_db,
        mock_repository.name,
        "archive-2024",
        stats=None,
        completion_time=None,
        job_name="Daily Backup"
    )

    # Assert
    call_args = apprise_instance.notify.call_args[1]
    assert call_args['title'] == "[SUCCESS] Backup Successful"
    assert "Daily Backup" not in call_args['title']


@pytest.mark.asyncio
async def test_json_data_in_body_for_json_webhook(test_db, mock_apprise, mock_repository):
    """Test that JSON data is included in body for JSON webhooks"""
    # Setup notification setting with JSON webhook URL
    setting = NotificationSettings(
        name="JSON Webhook Alert",
        service_url="jsons://webhook.site/test",
        enabled=True,
        notify_on_backup_success=True,
        monitor_all_repositories=True
    )
    test_db.add(setting)
    test_db.commit()

    # Setup mock
    apprise_instance = mock_apprise.return_value
    apprise_instance.add.return_value = True
    apprise_instance.notify.return_value = True

    # Action
    stats = {"original_size": 1024, "compressed_size": 512}
    await notification_service.send_backup_success(
        test_db,
        mock_repository.name,
        "archive-2024",
        stats=stats,
        completion_time=None,
        job_name="Daily Backup"
    )

    # Assert
    call_args = apprise_instance.notify.call_args[1]
    body = call_args['body']

    # Body should be pure compact JSON
    import json as json_module
    parsed = json_module.loads(body)
    assert parsed["event_type"] == "backup_success"
    assert parsed["repository_name"] == mock_repository.name
    assert parsed["archive_name"] == "archive-2024"
    assert parsed["job_name"] == "Daily Backup"
    assert parsed["stats"]["original_size"] == 1024

    # Should NOT contain markdown formatting
    assert 'JSON Data' not in body
    assert '```json' not in body


@pytest.mark.asyncio
async def test_json_data_not_in_body_for_non_json_services(test_db, mock_apprise, mock_repository):
    """Test that JSON data is NOT included for non-JSON webhook services"""
    # Setup notification setting with non-JSON service
    setting = NotificationSettings(
        name="Slack Alert",
        service_url="slack://token/channel",
        enabled=True,
        notify_on_backup_success=True,
        monitor_all_repositories=True
    )
    test_db.add(setting)
    test_db.commit()

    # Setup mock
    apprise_instance = mock_apprise.return_value
    apprise_instance.add.return_value = True
    apprise_instance.notify.return_value = True

    # Action
    await notification_service.send_backup_success(
        test_db,
        mock_repository.name,
        "archive-2024",
        stats=None,
        completion_time=None,
        job_name="Daily Backup"
    )

    # Assert
    call_args = apprise_instance.notify.call_args[1]
    body = call_args['body']

    # Check JSON is NOT present
    assert 'JSON Data' not in body
    assert '```json' not in body
    assert '"event_type"' not in body


@pytest.mark.asyncio
async def test_json_format_for_json_webhook_uses_compact_format(test_db, mock_apprise, mock_repository):
    """Test that JSON webhooks get compact JSON (not HTML formatted)"""
    # Setup JSON webhook notification
    setting = NotificationSettings(
        name="JSON Webhook Alert",
        service_url="jsons://webhook.site/test",
        enabled=True,
        notify_on_backup_failure=True,
        monitor_all_repositories=True
    )
    test_db.add(setting)
    test_db.commit()

    # Setup mock
    apprise_instance = mock_apprise.return_value
    apprise_instance.add.return_value = True
    apprise_instance.notify.return_value = True

    # Action
    await notification_service.send_backup_failure(
        test_db,
        mock_repository.name,
        "Connection error",
        job_id=123,
        job_name="Nightly Backup"
    )

    # Assert
    call_args = apprise_instance.notify.call_args[1]
    body = call_args['body']

    # Body should be pure compact JSON (no HTML, no markdown)
    import json as json_module
    parsed = json_module.loads(body)
    assert parsed["event_type"] == "backup_failure"
    assert parsed["error_message"] == "Connection error"
    assert parsed["job_name"] == "Nightly Backup"

    # Should NOT contain HTML or markdown formatting
    assert '<details>' not in body
    assert '```json' not in body
    assert 'JSON Data' not in body


@pytest.mark.asyncio
async def test_all_notification_methods_support_job_name(test_db, mock_apprise, mock_repository):
    """Test that all notification methods accept job_name parameter"""
    # Setup notification setting
    setting = NotificationSettings(
        name="Test Alert",
        service_url="slack://token/channel",
        enabled=True,
        notify_on_backup_start=True,
        notify_on_backup_success=True,
        notify_on_backup_failure=True,
        notify_on_restore_success=True,
        notify_on_restore_failure=True,
        notify_on_schedule_failure=True,
        notify_on_check_success=True,
        notify_on_check_failure=True,
        include_job_name_in_title=True,
        monitor_all_repositories=True
    )
    test_db.add(setting)
    test_db.commit()

    # Setup mock
    apprise_instance = mock_apprise.return_value
    apprise_instance.add.return_value = True
    apprise_instance.notify.return_value = True

    job_name = "Test Job"

    # Test all methods
    await notification_service.send_backup_start(
        test_db, mock_repository.name, "archive", None, None, job_name
    )
    assert "Test Job" in apprise_instance.notify.call_args[1]['title']

    await notification_service.send_backup_success(
        test_db, mock_repository.name, "archive", None, None, job_name
    )
    assert "Test Job" in apprise_instance.notify.call_args[1]['title']

    await notification_service.send_backup_failure(
        test_db, mock_repository.name, "error", None, job_name
    )
    assert "Test Job" in apprise_instance.notify.call_args[1]['title']

    await notification_service.send_restore_success(
        test_db, mock_repository.name, "archive", "/dest", None, job_name
    )
    assert "Test Job" in apprise_instance.notify.call_args[1]['title']

    await notification_service.send_restore_failure(
        test_db, mock_repository.name, "archive", "error", job_name
    )
    assert "Test Job" in apprise_instance.notify.call_args[1]['title']

    await notification_service.send_check_completion(
        test_db, mock_repository.name, "/path", "completed", None, None, "manual", job_name
    )
    assert "Test Job" in apprise_instance.notify.call_args[1]['title']


@pytest.mark.asyncio
async def test_json_webhook_receives_pure_json(test_db, mock_apprise, mock_repository):
    """Test that JSON webhooks automatically receive pure JSON (compact format)"""
    # Setup JSON webhook notification - JSON is automatic for json:// URLs
    setting = NotificationSettings(
        name="JSON Webhook",
        service_url="jsons://webhook.site/test-123",
        enabled=True,
        notify_on_backup_success=True,
        monitor_all_repositories=True
    )
    test_db.add(setting)
    test_db.commit()

    # Setup mock
    apprise_instance = mock_apprise.return_value
    apprise_instance.add.return_value = True
    apprise_instance.notify.return_value = True

    # Action
    stats = {"original_size": 1024, "compressed_size": 512}
    await notification_service.send_backup_success(
        test_db,
        mock_repository.name,
        "archive-2024",
        stats=stats,
        completion_time=None,
        job_name="Daily Backup"
    )

    # Assert
    call_args = apprise_instance.notify.call_args[1]
    body = call_args['body']

    # Body should be pure JSON string (parseable)
    parsed = json_module.loads(body)
    assert parsed["event_type"] == "backup_success"
    assert parsed["repository_name"] == mock_repository.name
    assert parsed["archive_name"] == "archive-2024"
    assert parsed["job_name"] == "Daily Backup"

    # Should NOT contain markdown formatting
    assert '```json' not in body
    assert '**JSON Data' not in body
    assert '<details>' not in body


@pytest.mark.asyncio
async def test_webhook_json_has_correct_repository_name_when_called_with_path(test_db, mock_apprise):
    """
    Test for bug: When notification is called with repository PATH,
    the JSON webhook should have repository_name as the NAME (not path).

    This simulates the real scenario where backup_service calls
    notification_service.send_backup_start(db, repository_path, ...)
    but the webhook JSON should have the friendly name.
    """
    # Create a repository where name != path (important for this test)
    repo = Repository(name="My Backup Repo", path="/tmp/backup-repo")
    test_db.add(repo)
    test_db.commit()
    test_db.refresh(repo)

    # Setup JSON webhook notification
    setting = NotificationSettings(
        name="JSON Webhook",
        service_url="jsons://webhook.site/test",
        enabled=True,
        notify_on_backup_start=True,
        notify_on_backup_success=True,
        notify_on_backup_failure=True,
        notify_on_restore_success=True,
        monitor_all_repositories=True
    )
    test_db.add(setting)
    test_db.commit()

    # Setup mock
    apprise_instance = mock_apprise.return_value
    apprise_instance.add.return_value = True
    apprise_instance.notify.return_value = True

    # ========== Test send_backup_start ==========
    # Call with PATH (this is how backup_service actually calls it)
    await notification_service.send_backup_start(
        test_db,
        repo.path,  # <-- Passing PATH, not name
        "archive-2024",
        source_directories=["/home/user/data"],
        expected_size=1024,
        job_name="Daily Backup"
    )

    # Parse the JSON body
    call_args = apprise_instance.notify.call_args[1]
    body = call_args['body']
    parsed = json_module.loads(body)

    # Assert: repository_name should be the NAME, not the PATH
    assert parsed["repository_name"] == "My Backup Repo", \
        f"Expected repository_name='My Backup Repo', got '{parsed['repository_name']}'"
    assert parsed["repository_path"] == "/tmp/backup-repo", \
        f"Expected repository_path='/tmp/backup-repo', got '{parsed['repository_path']}'"

    # ========== Test send_backup_success ==========
    await notification_service.send_backup_success(
        test_db,
        repo.path,  # <-- Passing PATH, not name
        "archive-2024",
        stats={"original_size": 1024},
        job_name="Daily Backup"
    )

    body = apprise_instance.notify.call_args[1]['body']
    parsed = json_module.loads(body)

    assert parsed["repository_name"] == "My Backup Repo", \
        f"Expected repository_name='My Backup Repo', got '{parsed['repository_name']}'"
    assert parsed["repository_path"] == "/tmp/backup-repo"

    # ========== Test send_backup_failure ==========
    await notification_service.send_backup_failure(
        test_db,
        repo.path,  # <-- Passing PATH, not name
        "Test error",
        job_id=123,
        job_name="Daily Backup"
    )

    body = apprise_instance.notify.call_args[1]['body']
    parsed = json_module.loads(body)

    assert parsed["repository_name"] == "My Backup Repo", \
        f"Expected repository_name='My Backup Repo', got '{parsed['repository_name']}'"
    assert parsed["repository_path"] == "/tmp/backup-repo"

    # ========== Test send_restore_success ==========
    await notification_service.send_restore_success(
        test_db,
        repo.path,  # <-- Passing PATH, not name
        "archive-2024",
        "/restore/dest",
        job_name="Restore Job"
    )

    body = apprise_instance.notify.call_args[1]['body']
    parsed = json_module.loads(body)

    assert parsed["repository_name"] == "My Backup Repo", \
        f"Expected repository_name='My Backup Repo', got '{parsed['repository_name']}'"
    assert parsed["repository_path"] == "/tmp/backup-repo"


@pytest.mark.asyncio
async def test_ssh_url_sanitization_in_notifications(test_db, mock_apprise):
    """Test that SSH URLs in notifications have username removed to prevent @ mentions"""
    # Create SSH repository with username in path
    ssh_repo = Repository(
        name="SSH Backup Repo",
        path="ssh://u331525-sub1@u331525-sub1.your-storagebox.de:23/home/BorgTestRepoKaran"
    )
    test_db.add(ssh_repo)
    test_db.commit()
    test_db.refresh(ssh_repo)

    # Setup notification setting
    setting = NotificationSettings(
        name="Discord Alert",
        service_url="discord://webhook_id/token",
        enabled=True,
        notify_on_backup_start=True,
        notify_on_backup_success=True,
        notify_on_backup_failure=True,
        notify_on_restore_success=True,
        notify_on_restore_failure=True,
        monitor_all_repositories=True
    )
    test_db.add(setting)
    test_db.commit()

    # Setup mock
    apprise_instance = mock_apprise.return_value
    apprise_instance.add.return_value = True
    apprise_instance.notify.return_value = True

    # Test backup_start
    await notification_service.send_backup_start(
        test_db,
        ssh_repo.name,
        "archive-2024",
        source_directories=["/data"]
    )
    call_args = apprise_instance.notify.call_args[1]
    body = call_args['body']
    assert "ssh://u331525-sub1.your-storagebox.de:23" in body  # Username removed
    # Verify username @ is not in Location line
    for line in body.split('\n'):
        if 'Location' in line and 'ssh://' in line:
            assert '@' not in line, f"Found @ in Location line: {line}"

    # Test backup_success
    await notification_service.send_backup_success(
        test_db,
        ssh_repo.name,
        "archive-2024",
        stats={"original_size": 1024}
    )
    call_args = apprise_instance.notify.call_args[1]
    body = call_args['body']
    assert "ssh://u331525-sub1.your-storagebox.de:23" in body
    for line in body.split('\n'):
        if 'Location' in line and 'ssh://' in line:
            assert '@' not in line, f"Found @ in Location line: {line}"

    # Test backup_failure
    await notification_service.send_backup_failure(
        test_db,
        ssh_repo.name,
        "Connection error",
        job_id=123
    )
    call_args = apprise_instance.notify.call_args[1]
    body = call_args['body']
    assert "ssh://u331525-sub1.your-storagebox.de:23" in body
    for line in body.split('\n'):
        if 'Location' in line and 'ssh://' in line:
            assert '@' not in line, f"Found @ in Location line: {line}"

    # Test restore_success
    await notification_service.send_restore_success(
        test_db,
        ssh_repo.name,
        "archive-2024",
        "/restore/dest"
    )
    call_args = apprise_instance.notify.call_args[1]
    body = call_args['body']
    assert "ssh://u331525-sub1.your-storagebox.de:23" in body
    for line in body.split('\n'):
        if 'Location' in line and 'ssh://' in line:
            assert '@' not in line, f"Found @ in Location line: {line}"

    # Test restore_failure
    await notification_service.send_restore_failure(
        test_db,
        ssh_repo.name,
        "archive-2024",
        "Restore failed"
    )
    call_args = apprise_instance.notify.call_args[1]
    body = call_args['body']
    assert "ssh://u331525-sub1.your-storagebox.de:23" in body
    for line in body.split('\n'):
        if 'Location' in line and 'ssh://' in line:
            assert '@' not in line, f"Found @ in Location line: {line}"


@pytest.mark.asyncio
async def test_local_repo_urls_unchanged(test_db, mock_apprise):
    """Test that local repository paths are not affected by SSH sanitization"""
    # Create local repository
    local_repo = Repository(
        name="Local Backup Repo",
        path="/local/path/to/repo"
    )
    test_db.add(local_repo)
    test_db.commit()
    test_db.refresh(local_repo)

    # Setup notification setting
    setting = NotificationSettings(
        name="Slack Alert",
        service_url="slack://token/channel",
        enabled=True,
        notify_on_backup_success=True,
        monitor_all_repositories=True
    )
    test_db.add(setting)
    test_db.commit()

    # Setup mock
    apprise_instance = mock_apprise.return_value
    apprise_instance.add.return_value = True
    apprise_instance.notify.return_value = True

    # Test
    await notification_service.send_backup_success(
        test_db,
        local_repo.name,
        "archive-2024",
        stats={"original_size": 1024}
    )

    # Assert - local path should be unchanged
    call_args = apprise_instance.notify.call_args[1]
    body = call_args['body']
    assert "/local/path/to/repo" in body
