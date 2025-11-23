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
            line-height: 1.6;
            color: #333;
            max-width: 600px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f5f5f5;
        }
        .email-container {
            background-color: #ffffff;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            overflow: hidden;
        }
        .email-header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px 20px;
            text-align: center;
        }
        .email-header h1 {
            margin: 0;
            font-size: 24px;
            font-weight: 600;
        }
        .email-body {
            padding: 30px 20px;
        }
        .info-section {
            margin-bottom: 25px;
        }
        .info-row {
            display: flex;
            padding: 12px 0;
            border-bottom: 1px solid #eee;
        }
        .info-row:last-child {
            border-bottom: none;
        }
        .info-label {
            font-weight: 600;
            color: #555;
            min-width: 140px;
            flex-shrink: 0;
        }
        .info-value {
            color: #333;
            word-break: break-word;
        }
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 15px;
            margin: 20px 0;
        }
        .stat-card {
            background-color: #f8f9fa;
            border-left: 4px solid #667eea;
            padding: 15px;
            border-radius: 4px;
        }
        .stat-label {
            font-size: 12px;
            color: #666;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-bottom: 5px;
        }
        .stat-value {
            font-size: 20px;
            font-weight: 600;
            color: #333;
        }
        .email-footer {
            background-color: #f8f9fa;
            padding: 20px;
            text-align: center;
            font-size: 13px;
            color: #666;
            border-top: 1px solid #eee;
        }
        .success-icon {
            font-size: 48px;
            margin-bottom: 10px;
        }
        .error-box {
            background-color: #fff3cd;
            border-left: 4px solid #ffc107;
            padding: 15px;
            margin: 15px 0;
            border-radius: 4px;
        }
        .error-box pre {
            margin: 10px 0 0 0;
            padding: 10px;
            background-color: #fff;
            border-radius: 4px;
            overflow-x: auto;
            font-size: 12px;
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
    async def send_backup_success(
        db: Session,
        repository_name: str,
        archive_name: str,
        stats: Optional[dict] = None
    ) -> None:
        """
        Send notification for successful backup.

        Args:
            db: Database session
            repository_name: Name of repository
            archive_name: Name of created archive
            stats: Backup statistics (optional)
        """
        settings = db.query(NotificationSettings).filter(
            NotificationSettings.enabled == True,
            NotificationSettings.notify_on_backup_success == True
        ).all()

        if not settings:
            return

        # Build content blocks for HTML email
        content_blocks = [
            {'label': 'Archive', 'value': archive_name},
            {'label': 'Repository', 'value': repository_name},
        ]

        # Add statistics as a grid if available
        if stats:
            stats_html = '<div class="stats-grid">'

            if "original_size" in stats and stats["original_size"]:
                stats_html += f'''
                <div class="stat-card">
                    <div class="stat-label">Original Size</div>
                    <div class="stat-value">{_format_bytes(stats['original_size'])}</div>
                </div>'''

            if "compressed_size" in stats and stats["compressed_size"]:
                stats_html += f'''
                <div class="stat-card">
                    <div class="stat-label">Compressed</div>
                    <div class="stat-value">{_format_bytes(stats['compressed_size'])}</div>
                </div>'''

            if "deduplicated_size" in stats and stats["deduplicated_size"] is not None:
                stats_html += f'''
                <div class="stat-card">
                    <div class="stat-label">Deduplicated</div>
                    <div class="stat-value">{_format_bytes(stats['deduplicated_size'])}</div>
                </div>'''

            stats_html += '</div>'
            content_blocks.append({'html': stats_html})

        # Create HTML body
        html_body = _create_html_email(
            title="✅ Backup Successful",
            content_blocks=content_blocks,
            footer=f"Completed at {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC"
        )

        # Fallback plain text body for non-HTML clients
        body_lines = [
            f"Archive: {archive_name}",
            f"Repository: {repository_name}",
        ]
        if stats:
            body_lines.append("")
            body_lines.append("Statistics:")
            if "original_size" in stats and stats["original_size"]:
                body_lines.append(f"  • Original size: {_format_bytes(stats['original_size'])}")
            if "compressed_size" in stats and stats["compressed_size"]:
                body_lines.append(f"  • Compressed size: {_format_bytes(stats['compressed_size'])}")
            if "deduplicated_size" in stats and stats["deduplicated_size"] is not None:
                body_lines.append(f"  • Deduplicated size: {_format_bytes(stats['deduplicated_size'])}")
        body_lines.append("")
        body_lines.append(f"✓ Completed at {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")
        text_body = "\n".join(body_lines)

        for setting in settings:
            title = "✅ Backup Successful"
            if setting.title_prefix:
                title = f"{setting.title_prefix} {title}"

            await NotificationService._send_to_service(db, setting, title, html_body, text_body)

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

        # Build content blocks for HTML
        content_blocks = [
            {'label': 'Repository', 'value': repository_name},
        ]

        if job_id:
            content_blocks.append({'label': 'Job ID', 'value': str(job_id)})

        # Add error box
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
            footer=f"Failed at {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC"
        )

        # Fallback plain text body
        body_lines = [
            f"Repository: {repository_name}",
            "",
            "Error Details:",
            f"  {error_message}",
        ]
        if job_id:
            body_lines.append("")
            body_lines.append(f"Job ID: {job_id}")
        body_lines.append("")
        body_lines.append(f"⚠ Failed at {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")
        text_body = "\n".join(body_lines)

        for setting in settings:
            title = "❌ Backup Failed"
            if setting.title_prefix:
                title = f"{setting.title_prefix} {title}"

            await NotificationService._send_to_service(db, setting, title, html_body, text_body)

    @staticmethod
    async def send_restore_success(
        db: Session,
        repository_name: str,
        archive_name: str,
        target_path: str
    ) -> None:
        """
        Send notification for successful restore.

        Args:
            db: Database session
            repository_name: Name of repository
            archive_name: Name of restored archive
            target_path: Restore destination
        """
        settings = db.query(NotificationSettings).filter(
            NotificationSettings.enabled == True,
            NotificationSettings.notify_on_restore_success == True
        ).all()

        if not settings:
            return

        # Build content blocks for HTML
        content_blocks = [
            {'label': 'Archive', 'value': archive_name},
            {'label': 'Repository', 'value': repository_name},
            {'label': 'Destination', 'value': target_path},
        ]

        html_body = _create_html_email(
            title="✅ Restore Successful",
            content_blocks=content_blocks,
            footer=f"Completed at {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC"
        )

        # Fallback plain text
        text_body = f"""Archive: {archive_name}
Repository: {repository_name}
Destination: {target_path}

✓ Completed at {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC"""

        for setting in settings:
            title = "✅ Restore Successful"
            if setting.title_prefix:
                title = f"{setting.title_prefix} {title}"

            await NotificationService._send_to_service(db, setting, title, html_body, text_body)

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

        # Build content blocks for HTML
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
            footer=f"Failed at {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC"
        )

        # Fallback plain text
        text_body = f"""Archive: {archive_name}
Repository: {repository_name}

Error Details:
  {error_message}

⚠ Failed at {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC"""

        for setting in settings:
            title = "❌ Restore Failed"
            if setting.title_prefix:
                title = f"{setting.title_prefix} {title}"

            await NotificationService._send_to_service(db, setting, title, html_body, text_body)

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

        # Build content blocks for HTML
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
            footer=f"Failed at {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC"
        )

        # Fallback plain text
        text_body = f"""Schedule: {schedule_name}
Repository: {repository_name}

Error Details:
  {error_message}

⚠ Failed at {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC"""

        for setting in settings:
            title = "❌ Scheduled Backup Failed"
            if setting.title_prefix:
                title = f"{setting.title_prefix} {title}"

            await NotificationService._send_to_service(db, setting, title, html_body, text_body)

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
        body: str,
        body_format: str = None
    ) -> None:
        """
        Send notification to a single service.

        Args:
            db: Database session
            setting: Notification setting
            title: Notification title
            body: Notification body (HTML or plain text)
            body_format: Optional plain text fallback for HTML emails
        """
        try:
            apobj = apprise.Apprise()
            apobj.add(setting.service_url)

            # Determine body format - use HTML if body looks like HTML
            notify_type = apprise.NotifyType.INFO

            # For email services, use HTML format if body contains HTML tags
            if body_format:
                # Send HTML with plain text fallback
                success = apobj.notify(
                    title=title,
                    body=body,
                    body_format=apprise.NotifyFormat.HTML
                )
            elif '<html' in body.lower() or '<div' in body.lower():
                # Looks like HTML
                success = apobj.notify(
                    title=title,
                    body=body,
                    body_format=apprise.NotifyFormat.HTML
                )
            else:
                # Plain text
                success = apobj.notify(title=title, body=body)

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
