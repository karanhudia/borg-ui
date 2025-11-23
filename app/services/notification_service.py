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

        # Format body with better structure
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

        body = "\n".join(body_lines)

        for setting in settings:
            title = "✅ Backup Successful"
            if setting.title_prefix:
                title = f"{setting.title_prefix} {title}"

            await NotificationService._send_to_service(db, setting, title, body)

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

        # Format body with better structure
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

        body = "\n".join(body_lines)

        for setting in settings:
            title = "❌ Backup Failed"
            if setting.title_prefix:
                title = f"{setting.title_prefix} {title}"

            await NotificationService._send_to_service(db, setting, title, body)

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

        # Format body with better structure
        body_lines = [
            f"Archive: {archive_name}",
            f"Repository: {repository_name}",
            f"Destination: {target_path}",
            "",
            f"✓ Completed at {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC"
        ]

        body = "\n".join(body_lines)

        for setting in settings:
            title = "✅ Restore Successful"
            if setting.title_prefix:
                title = f"{setting.title_prefix} {title}"

            await NotificationService._send_to_service(db, setting, title, body)

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

        # Format body with better structure
        body_lines = [
            f"Archive: {archive_name}",
            f"Repository: {repository_name}",
            "",
            "Error Details:",
            f"  {error_message}",
            "",
            f"⚠ Failed at {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC"
        ]

        body = "\n".join(body_lines)

        for setting in settings:
            title = "❌ Restore Failed"
            if setting.title_prefix:
                title = f"{setting.title_prefix} {title}"

            await NotificationService._send_to_service(db, setting, title, body)

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

        # Format body with better structure
        body_lines = [
            f"Schedule: {schedule_name}",
            f"Repository: {repository_name}",
            "",
            "Error Details:",
            f"  {error_message}",
            "",
            f"⚠ Failed at {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC"
        ]

        body = "\n".join(body_lines)

        for setting in settings:
            title = "❌ Scheduled Backup Failed"
            if setting.title_prefix:
                title = f"{setting.title_prefix} {title}"

            await NotificationService._send_to_service(db, setting, title, body)

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
        body: str
    ) -> None:
        """
        Send notification to a single service.

        Args:
            db: Database session
            setting: Notification setting
            title: Notification title
            body: Notification body
        """
        try:
            apobj = apprise.Apprise()
            apobj.add(setting.service_url)

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
