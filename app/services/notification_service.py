"""
Notification service using Apprise.

Handles sending notifications for backup/restore events.
"""

import apprise
from typing import Optional, List
from sqlalchemy.orm import Session
from datetime import datetime
import structlog

from app.database.models import NotificationSettings

logger = structlog.get_logger()


def _format_bytes(bytes_value: int) -> str:
    """Format bytes into human-readable size."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_value < 1024.0:
            return f"{bytes_value:.2f} {unit}"
        bytes_value /= 1024.0
    return f"{bytes_value:.2f} PB"


def _create_markdown_message(title: str, content_blocks: list, footer: str = None) -> str:
    """
    Create a well-formatted Markdown message for chat services (Slack, Discord, Telegram, etc.).

    Args:
        title: Message title/header
        content_blocks: List of dicts with 'label'/'value' pairs or 'html' key (ignored for markdown)
        footer: Optional footer text

    Returns:
        Markdown formatted string
    """
    lines = [f"**{title}**", ""]

    for block in content_blocks:
        if 'label' in block and 'value' in block:
            lines.append(f"**{block['label']}:** {block['value']}")
        elif 'html' in block:
            # Skip HTML blocks - these are statistics that we'll format differently
            # Extract stats from the HTML if needed, or just skip for now
            pass

    if footer:
        lines.append("")
        lines.append(f"_{footer}_")

    return "\n".join(lines)


def _is_email_service(service_url: str) -> bool:
    """Check if the service URL is for an email service."""
    email_prefixes = ['mailto://', 'mailtos://', 'smtp://', 'smtps://']
    return any(service_url.lower().startswith(prefix) for prefix in email_prefixes)


def _create_html_email(title: str, content_blocks: list, footer: str = None) -> str:
    """
    Create a well-formatted HTML email template.

    Args:
        title: Email title
        content_blocks: List of content sections (each is a dict with 'label' and 'value' or 'html')
        footer: Optional footer text

    Returns:
        HTML string
    """
    html_parts = ['''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            line-height: 1.4;
            color: #333;
            max-width: 600px;
            margin: 0 auto;
            padding: 10px;
            background-color: #f5f5f5;
        }
        .email-container {
            background-color: #ffffff;
            border-radius: 6px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            overflow: hidden;
        }
        .email-header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 16px;
            text-align: center;
        }
        .email-header h1 {
            margin: 0;
            font-size: 18px;
            font-weight: 600;
        }
        .email-body {
            padding: 16px;
        }
        .info-row {
            display: flex;
            padding: 8px 0;
            border-bottom: 1px solid #eee;
            font-size: 14px;
        }
        .info-row:last-child {
            border-bottom: none;
        }
        .info-label {
            font-weight: 600;
            color: #555;
            min-width: 100px;
            flex-shrink: 0;
        }
        .info-value {
            color: #333;
            word-break: break-word;
        }
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 10px;
            margin: 12px 0;
        }
        .stat-card {
            background-color: #f8f9fa;
            border-left: 3px solid #667eea;
            padding: 10px;
            border-radius: 3px;
        }
        .stat-label {
            font-size: 10px;
            color: #666;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-bottom: 4px;
        }
        .stat-value {
            font-size: 16px;
            font-weight: 600;
            color: #333;
        }
        .email-footer {
            background-color: #f8f9fa;
            padding: 12px;
            text-align: center;
            font-size: 12px;
            color: #666;
            border-top: 1px solid #eee;
        }
        .error-box {
            background-color: #fff3cd;
            border-left: 3px solid #ffc107;
            padding: 10px;
            margin: 10px 0;
            border-radius: 3px;
            font-size: 13px;
        }
        .error-box pre {
            margin: 8px 0 0 0;
            padding: 8px;
            background-color: #fff;
            border-radius: 3px;
            overflow-x: auto;
            font-size: 11px;
        }
    </style>
</head>
<body>
    <div class="email-container">
        <div class="email-header">
            <h1>''' + title + '''</h1>
        </div>
        <div class="email-body">
''']

    for block in content_blocks:
        if 'html' in block:
            html_parts.append(block['html'])
        elif 'label' in block and 'value' in block:
            html_parts.append(f'''
            <div class="info-row">
                <div class="info-label">{block['label']}:</div>
                <div class="info-value">{block['value']}</div>
            </div>
''')

    html_parts.append('''
        </div>
''')

    if footer:
        html_parts.append(f'''
        <div class="email-footer">
            {footer}
        </div>
''')

    html_parts.append('''
    </div>
</body>
</html>
''')

    return ''.join(html_parts)


class NotificationService:
    """Service for sending notifications via Apprise."""

    @staticmethod
    async def send_backup_start(
        db: Session,
        repository_name: str,
        archive_name: str,
        source_directories: Optional[list] = None,
        expected_size: Optional[int] = None
    ) -> None:
        """
        Send notification when backup starts.

        Args:
            db: Database session
            repository_name: Name of repository
            archive_name: Name of archive being created
            source_directories: List of source directories being backed up (optional)
            expected_size: Expected total size in bytes (optional)
        """
        settings = db.query(NotificationSettings).filter(
            NotificationSettings.enabled == True,
            NotificationSettings.notify_on_backup_start == True
        ).all()

        if not settings:
            return

        # Build content blocks
        content_blocks = [
            {'label': 'Archive', 'value': archive_name},
            {'label': 'Repository', 'value': repository_name},
        ]

        # Add source directories if provided
        if source_directories:
            sources_text = "\n".join(f"• {src}" for src in source_directories)
            content_blocks.append({'label': 'Sources', 'value': sources_text})

        # Add expected size if provided
        if expected_size:
            content_blocks.append({'label': 'Expected Size', 'value': _format_bytes(expected_size)})

        # Create timestamp
        start_time = datetime.now()
        timestamp_str = start_time.strftime('%Y-%m-%d %H:%M:%S')

        # Create HTML body for email
        html_body = _create_html_email(
            title="🚀 Backup Started",
            content_blocks=content_blocks,
            timestamp_label="Started at",
            timestamp=timestamp_str
        )

        # Create markdown body for chat services
        markdown_body = _create_markdown_message(
            title="🚀 Backup Started",
            content_blocks=content_blocks,
            timestamp_label="Started at",
            timestamp=timestamp_str
        )

        # Send to all enabled services with this event trigger
        for setting in settings:
            await NotificationService._send_to_service(
                setting=setting,
                html_body=html_body,
                markdown_body=markdown_body,
                title_suffix="Backup Started",
                db=db
            )

    @staticmethod
    async def send_backup_success(
        db: Session,
        repository_name: str,
        archive_name: str,
        stats: Optional[dict] = None,
        completion_time: Optional[datetime] = None
    ) -> None:
        """
        Send notification for successful backup.

        Args:
            db: Database session
            repository_name: Name of repository
            archive_name: Name of created archive
            stats: Backup statistics (optional)
            completion_time: When the backup completed (optional, defaults to now)
        """
        settings = db.query(NotificationSettings).filter(
            NotificationSettings.enabled == True,
            NotificationSettings.notify_on_backup_success == True
        ).all()

        if not settings:
            return

        # Build content blocks for HTML email and markdown
        content_blocks = [
            {'label': 'Archive', 'value': archive_name},
            {'label': 'Repository', 'value': repository_name},
        ]

        # Add statistics as a grid for HTML, and as simple blocks for markdown
        stats_blocks = []
        if stats:
            stats_html = '<div class="stats-grid">'

            if "original_size" in stats and stats["original_size"]:
                stats_html += f'''
                <div class="stat-card">
                    <div class="stat-label">Original Size</div>
                    <div class="stat-value">{_format_bytes(stats['original_size'])}</div>
                </div>'''
                stats_blocks.append({'label': 'Original Size', 'value': _format_bytes(stats['original_size'])})

            if "compressed_size" in stats and stats["compressed_size"]:
                stats_html += f'''
                <div class="stat-card">
                    <div class="stat-label">Compressed</div>
                    <div class="stat-value">{_format_bytes(stats['compressed_size'])}</div>
                </div>'''
                stats_blocks.append({'label': 'Compressed', 'value': _format_bytes(stats['compressed_size'])})

            if "deduplicated_size" in stats and stats["deduplicated_size"] is not None:
                stats_html += f'''
                <div class="stat-card">
                    <div class="stat-label">Deduplicated</div>
                    <div class="stat-value">{_format_bytes(stats['deduplicated_size'])}</div>
                </div>'''
                stats_blocks.append({'label': 'Deduplicated', 'value': _format_bytes(stats['deduplicated_size'])})

            stats_html += '</div>'
            content_blocks.append({'html': stats_html})

        # Use provided completion time or current time as fallback
        completed_at = completion_time or datetime.now()
        timestamp_str = completed_at.strftime('%Y-%m-%d %H:%M:%S')

        # Create content blocks for markdown (including stats)
        markdown_blocks = [
            {'label': 'Archive', 'value': archive_name},
            {'label': 'Repository', 'value': repository_name},
        ]
        markdown_blocks.extend(stats_blocks)

        # Create HTML body for email
        html_body = _create_html_email(
            title="✅ Backup Successful",
            content_blocks=content_blocks,
            footer=f"Completed at {timestamp_str}"
        )

        # Create Markdown body for chat services
        markdown_body = _create_markdown_message(
            title="✅ Backup Successful",
            content_blocks=markdown_blocks,
            footer=f"Completed at {timestamp_str}"
        )

        for setting in settings:
            title = "✅ Backup Successful"
            if setting.title_prefix:
                title = f"{setting.title_prefix} {title}"

            await NotificationService._send_to_service(db, setting, title, html_body, markdown_body)

    @staticmethod
    async def send_backup_failure(
        db: Session,
        repository_name: str,
        error_message: str,
        job_id: Optional[int] = None
    ) -> None:
        """
        Send notification for failed backup.

        Args:
            db: Database session
            repository_name: Name of repository
            error_message: Error description
            job_id: Backup job ID (optional)
        """
        settings = db.query(NotificationSettings).filter(
            NotificationSettings.enabled == True,
            NotificationSettings.notify_on_backup_failure == True
        ).all()

        if not settings:
            return

        # Build content blocks
        content_blocks = [
            {'label': 'Repository', 'value': repository_name},
        ]

        if job_id:
            content_blocks.append({'label': 'Job ID', 'value': str(job_id)})

        # Add error box for HTML
        error_html = f'''
        <div class="error-box">
            <strong>Error Details:</strong>
            <pre>{error_message}</pre>
        </div>'''
        content_blocks.append({'html': error_html})

        # Create HTML body
        html_body = _create_html_email(
            title="❌ Backup Failed",
            content_blocks=content_blocks,
            footer=f"Failed at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )

        # Create markdown body (without HTML error box)
        markdown_blocks = [
            {'label': 'Repository', 'value': repository_name},
        ]
        if job_id:
            markdown_blocks.append({'label': 'Job ID', 'value': str(job_id)})
        markdown_blocks.append({'label': 'Error', 'value': f"```\n{error_message}\n```"})

        markdown_body = _create_markdown_message(
            title="❌ Backup Failed",
            content_blocks=markdown_blocks,
            footer=f"Failed at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )

        for setting in settings:
            title = "❌ Backup Failed"
            if setting.title_prefix:
                title = f"{setting.title_prefix} {title}"

            await NotificationService._send_to_service(db, setting, title, html_body, markdown_body)

    @staticmethod
    async def send_restore_success(
        db: Session,
        repository_name: str,
        archive_name: str,
        target_path: str,
        completion_time: Optional[datetime] = None
    ) -> None:
        """
        Send notification for successful restore.

        Args:
            db: Database session
            repository_name: Name of repository
            archive_name: Name of restored archive
            target_path: Restore destination
            completion_time: When the restore completed (optional, defaults to now)
        """
        settings = db.query(NotificationSettings).filter(
            NotificationSettings.enabled == True,
            NotificationSettings.notify_on_restore_success == True
        ).all()

        if not settings:
            return

        # Build content blocks
        content_blocks = [
            {'label': 'Archive', 'value': archive_name},
            {'label': 'Repository', 'value': repository_name},
            {'label': 'Destination', 'value': target_path},
        ]

        # Use provided completion time or current time as fallback
        completed_at = completion_time or datetime.now()
        timestamp_str = completed_at.strftime('%Y-%m-%d %H:%M:%S')

        html_body = _create_html_email(
            title="✅ Restore Successful",
            content_blocks=content_blocks,
            footer=f"Completed at {timestamp_str}"
        )

        markdown_body = _create_markdown_message(
            title="✅ Restore Successful",
            content_blocks=content_blocks,
            footer=f"Completed at {timestamp_str}"
        )

        for setting in settings:
            title = "✅ Restore Successful"
            if setting.title_prefix:
                title = f"{setting.title_prefix} {title}"

            await NotificationService._send_to_service(db, setting, title, html_body, markdown_body)

    @staticmethod
    async def send_restore_failure(
        db: Session,
        repository_name: str,
        archive_name: str,
        error_message: str
    ) -> None:
        """
        Send notification for failed restore.

        Args:
            db: Database session
            repository_name: Name of repository
            archive_name: Name of archive
            error_message: Error description
        """
        settings = db.query(NotificationSettings).filter(
            NotificationSettings.enabled == True,
            NotificationSettings.notify_on_restore_failure == True
        ).all()

        if not settings:
            return

        # Build content blocks
        content_blocks = [
            {'label': 'Archive', 'value': archive_name},
            {'label': 'Repository', 'value': repository_name},
        ]

        error_html = f'''
        <div class="error-box">
            <strong>Error Details:</strong>
            <pre>{error_message}</pre>
        </div>'''
        content_blocks.append({'html': error_html})

        html_body = _create_html_email(
            title="❌ Restore Failed",
            content_blocks=content_blocks,
            footer=f"Failed at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )

        # Create markdown body
        markdown_blocks = [
            {'label': 'Archive', 'value': archive_name},
            {'label': 'Repository', 'value': repository_name},
            {'label': 'Error', 'value': f"```\n{error_message}\n```"},
        ]

        markdown_body = _create_markdown_message(
            title="❌ Restore Failed",
            content_blocks=markdown_blocks,
            footer=f"Failed at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )

        for setting in settings:
            title = "❌ Restore Failed"
            if setting.title_prefix:
                title = f"{setting.title_prefix} {title}"

            await NotificationService._send_to_service(db, setting, title, html_body, markdown_body)

    @staticmethod
    async def send_schedule_failure(
        db: Session,
        schedule_name: str,
        repository_name: str,
        error_message: str
    ) -> None:
        """
        Send notification for failed scheduled backup.

        Args:
            db: Database session
            schedule_name: Name of schedule
            repository_name: Name of repository
            error_message: Error description
        """
        settings = db.query(NotificationSettings).filter(
            NotificationSettings.enabled == True,
            NotificationSettings.notify_on_schedule_failure == True
        ).all()

        if not settings:
            return

        # Build content blocks
        content_blocks = [
            {'label': 'Schedule', 'value': schedule_name},
            {'label': 'Repository', 'value': repository_name},
        ]

        error_html = f'''
        <div class="error-box">
            <strong>Error Details:</strong>
            <pre>{error_message}</pre>
        </div>'''
        content_blocks.append({'html': error_html})

        html_body = _create_html_email(
            title="❌ Scheduled Backup Failed",
            content_blocks=content_blocks,
            footer=f"Failed at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )

        # Create markdown body
        markdown_blocks = [
            {'label': 'Schedule', 'value': schedule_name},
            {'label': 'Repository', 'value': repository_name},
            {'label': 'Error', 'value': f"```\n{error_message}\n```"},
        ]

        markdown_body = _create_markdown_message(
            title="❌ Scheduled Backup Failed",
            content_blocks=markdown_blocks,
            footer=f"Failed at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )

        for setting in settings:
            title = "❌ Scheduled Backup Failed"
            if setting.title_prefix:
                title = f"{setting.title_prefix} {title}"

            await NotificationService._send_to_service(db, setting, title, html_body, markdown_body)

    @staticmethod
    async def test_notification(service_url: str) -> dict:
        """
        Test a notification service URL.

        Args:
            service_url: Apprise service URL

        Returns:
            dict with success status and message
        """
        try:
            apobj = apprise.Apprise()
            result = apobj.add(service_url)

            if not result:
                # Try to provide helpful error message based on URL prefix
                service_type = service_url.split(':')[0] if ':' in service_url else 'unknown'
                return {
                    "success": False,
                    "message": f"Invalid URL format for '{service_type}' service. Please check the URL syntax. Example formats:\n" +
                               "• Email: mailtos://user:password@smtp.gmail.com\n" +
                               "• Slack: slack://TokenA/TokenB/TokenC/\n" +
                               "• Discord: discord://webhook_id/webhook_token\n" +
                               "• Telegram: telegram://bot_token/chat_id"
                }

            # Send test notification with detailed logging
            logger.info("Attempting to send test notification", service_url_prefix=service_url.split(':')[0])

            success = apobj.notify(
                title="🔔 Borg UI Test Notification",
                body="This is a test notification from Borg Web UI. If you received this, your notification service is configured correctly!"
            )

            if success:
                logger.info("Test notification sent successfully")
                return {
                    "success": True,
                    "message": "Test notification sent successfully! Check your inbox/service."
                }
            else:
                logger.error("Test notification failed to send", service_url_prefix=service_url.split(':')[0])
                return {
                    "success": False,
                    "message": "Failed to send test notification. Possible causes:\n" +
                               "• For Gmail: Check App Password is correct (16 chars, no spaces)\n" +
                               "• For Gmail: Ensure 2-Step Verification is enabled\n" +
                               "• Check SMTP server is reachable (firewall/network)\n" +
                               "• Verify credentials are correct"
                }

        except Exception as e:
            logger.error("notification_test_failed", error=str(e))
            return {
                "success": False,
                "message": f"Error: {str(e)}"
            }

    @staticmethod
    async def _send_to_service(
        db: Session,
        setting: NotificationSettings,
        title: str,
        html_body: str,
        markdown_body: str
    ) -> None:
        """
        Send notification to a single service.

        Automatically chooses the appropriate format based on service type:
        - Email services: HTML format
        - Chat services (Slack, Discord, Telegram, etc.): Markdown format

        Args:
            db: Database session
            setting: Notification setting
            title: Notification title
            html_body: HTML formatted body (for email)
            markdown_body: Markdown formatted body (for chat services)
        """
        try:
            apobj = apprise.Apprise()
            apobj.add(setting.service_url)

            # Choose format based on service type
            if _is_email_service(setting.service_url):
                # Email service - use HTML format
                success = apobj.notify(
                    title=title,
                    body=html_body,
                    body_format=apprise.NotifyFormat.HTML
                )
            else:
                # Chat service - use Markdown format
                success = apobj.notify(
                    title=title,
                    body=markdown_body,
                    body_format=apprise.NotifyFormat.MARKDOWN
                )

            if success:
                # Update last_used_at timestamp
                setting.last_used_at = datetime.utcnow()
                db.commit()
                logger.info(
                    "notification_sent",
                    service=setting.name,
                    title=title
                )
            else:
                logger.warning(
                    "notification_failed",
                    service=setting.name,
                    title=title
                )

        except Exception as e:
            logger.error(
                "notification_error",
                service=setting.name,
                error=str(e)
            )

    @staticmethod
    async def _send_to_services(
        db: Session,
        settings: List[NotificationSettings],
        title: str,
        body: str
    ) -> None:
        """
        Send notification to multiple services (legacy).

        Args:
            db: Database session
            settings: List of notification settings
            title: Notification title
            body: Notification body
        """
        for setting in settings:
            await NotificationService._send_to_service(db, setting, title, body)


# Global instance
notification_service = NotificationService()
