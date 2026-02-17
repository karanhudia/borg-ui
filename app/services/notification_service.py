"""
Notification service using Apprise.

Handles sending notifications for backup/restore events.
"""

import apprise
from typing import Optional, List
from sqlalchemy.orm import Session
from datetime import datetime
import structlog
import socket

from app.database.models import NotificationSettings, Repository

logger = structlog.get_logger()


def _get_repository(db: Session, name_or_path: str) -> Optional[Repository]:
    """Get repository by name or path."""
    from sqlalchemy import or_
    return db.query(Repository).filter(
        or_(
            Repository.name == name_or_path,
            Repository.path == name_or_path
        )
    ).first()


def _notification_applies_to_repository(
    db: Session,
    setting: NotificationSettings,
    repository_name_or_path: str
) -> bool:
    """
    Check if a notification setting applies to the given repository.

    Args:
        db: Database session
        setting: NotificationSettings object
        repository_name_or_path: Name or path of the repository

    Returns:
        True if notification should be sent, False otherwise
    """
    # If monitoring all repositories, always apply
    if setting.monitor_all_repositories:
        return True

    # If not monitoring all, check if this specific repository is in the list
    if not setting.repositories:
        return False

    # Get repository by name OR path to check if it's in the filtered list
    repo = _get_repository(db, repository_name_or_path)
    
    if not repo:
        # Try finding by partial path matching if exact match fails (common for SSH repos)
        # But for now let's stick to exact match and basic robust checks
        return False

    # Check if this repository ID is in the notification's filtered list
    # Use ID comparison for robustness
    setting_repo_ids = [r.id for r in setting.repositories]
    return repo.id in setting_repo_ids


def _format_bytes(bytes_value: int) -> str:
    """Format bytes into human-readable size."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_value < 1024.0:
            return f"{bytes_value:.2f} {unit}"
        bytes_value /= 1024.0
    return f"{bytes_value:.2f} PB"


def _format_duration(started_at: datetime, completed_at: datetime) -> str:
    """
    Format duration as human-readable string.

    Examples: '2h 34m', '5m 32s', '45s'
    """
    delta = completed_at - started_at
    total_seconds = int(delta.total_seconds())

    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60

    if hours > 0:
        return f"{hours}h {minutes}m"
    elif minutes > 0:
        return f"{minutes}m {seconds}s"
    else:
        return f"{seconds}s"


def _calculate_compression_ratio(original_size: int, compressed_size: int) -> str:
    """
    Calculate and format compression ratio.

    Returns: String like "28.5% (saved 2.1 GB)" or "No compression" if sizes are equal
    """
    if not original_size or original_size == 0:
        return "N/A"

    if compressed_size >= original_size:
        return "No compression"

    savings_bytes = original_size - compressed_size
    ratio = (savings_bytes / original_size) * 100

    return f"{ratio:.1f}% (saved {_format_bytes(savings_bytes)})"


def _calculate_backup_speed(total_bytes: int, duration_seconds: int) -> str:
    """
    Calculate average backup speed.

    Returns: String like "45.6 MB/s" or "N/A" if duration is zero
    """
    if not duration_seconds or duration_seconds == 0:
        return "N/A"

    bytes_per_second = total_bytes / duration_seconds

    # Convert to appropriate unit
    for unit in ['B/s', 'KB/s', 'MB/s', 'GB/s']:
        if bytes_per_second < 1024.0:
            return f"{bytes_per_second:.1f} {unit}"
        bytes_per_second /= 1024.0

    return f"{bytes_per_second:.1f} TB/s"


def _get_status_badge(status_type: str, is_html: bool = False) -> str:
    """
    Get professional status badge (text-based, no emojis).

    Args:
        status_type: One of 'success', 'failed', 'warning', 'info', 'started'
        is_html: If True, returns HTML span with color. If False, returns plain text badge.

    Returns:
        Professional status badge like "[SUCCESS]" or HTML colored badge
    """
    badge_configs = {
        'success': {'text': '[SUCCESS]', 'color': '#28a745'},
        'failed': {'text': '[FAILED]', 'color': '#dc3545'},
        'error': {'text': '[ERROR]', 'color': '#dc3545'},
        'warning': {'text': '[WARNING]', 'color': '#ffc107'},
        'info': {'text': '[INFO]', 'color': '#17a2b8'},
        'started': {'text': '[STARTED]', 'color': '#007bff'},
    }

    config = badge_configs.get(status_type.lower(), badge_configs['info'])

    if is_html:
        return f'<span style="background-color: {config["color"]}; color: white; padding: 3px 8px; border-radius: 3px; font-weight: 600; font-size: 12px;">{config["text"]}</span>'
    else:
        return config['text']


def _get_repository_type(repo) -> str:
    """
    Get repository type as a readable string.

    Args:
        repo: Repository object or None

    Returns:
        String like "Local", "SSH", "SFTP", or "Unknown"
    """
    if not repo:
        return "Unknown"

    # Check for SSH connection
    if hasattr(repo, 'ssh_connection_id') and repo.ssh_connection_id:
        return "SSH"

    # Check path patterns
    if hasattr(repo, 'path'):
        path = repo.path
        if path.startswith('ssh://'):
            return "SSH"
        elif path.startswith('sftp://'):
            return "SFTP"
        elif '/' in path or '\\' in path:
            return "Local"

    return "Unknown"


def _create_markdown_message(title: str, content_blocks: list, footer: str = None) -> str:
    """
    Create a well-formatted Markdown message for chat services (Slack, Discord, Telegram, etc.).

    Args:
        title: Message title/header (NOTE: Not included in body as Apprise displays it separately)
        content_blocks: List of dicts with 'label'/'value' pairs or 'html' key (ignored for markdown)
        footer: Optional footer text

    Returns:
        Markdown formatted string
    """
    # Note: Title is NOT included in the body because Apprise displays it separately
    # for chat services (Telegram, Slack, Discord, etc.)
    lines = []

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


def _is_webhook_service(service_url: str) -> bool:
    """Check if the service URL is for a webhook service."""
    webhook_prefixes = [
        'http://', 'https://',  # Generic webhooks
        'json://', 'jsons://',  # Apprise JSON webhooks
        'form://', 'forms://',  # Apprise form webhooks
        'xml://', 'xmls://'     # Apprise XML webhooks
    ]
    # Exclude email services that use HTTPS (like mailgun)
    if _is_email_service(service_url):
        return False
    return any(service_url.lower().startswith(prefix) for prefix in webhook_prefixes)


def _is_json_webhook(service_url: str) -> bool:
    """Check if the service URL is specifically for a JSON webhook."""
    json_prefixes = ['json://', 'jsons://']
    return any(service_url.lower().startswith(prefix) for prefix in json_prefixes)


def _should_include_json(setting: NotificationSettings) -> bool:
    """
    Determine if JSON should be included in notification body.

    JSON is automatically sent for json:// and jsons:// webhook URLs.
    This is the primary use case for structured data in notifications.

    Args:
        setting: NotificationSettings object

    Returns:
        True if service_url is a JSON webhook (json:// or jsons://)
    """
    return _is_json_webhook(setting.service_url)


def _build_json_data(event_type: str, data: dict, compact: bool = False) -> str:
    """
    Build structured JSON data for notifications.

    Args:
        event_type: Type of event (backup_success, backup_failure, etc.)
        data: Event data dictionary
        compact: If True, returns compact JSON (no indentation). If False, returns pretty-printed JSON.

    Returns:
        JSON string formatted for inclusion in notification body
    """
    import json

    json_data = {
        "event_type": event_type,
        "timestamp": datetime.now().isoformat(),
        **data
    }

    if compact:
        return json.dumps(json_data)
    else:
        return json.dumps(json_data, indent=2)


def _append_json_to_body(body: str, json_data: str, is_html: bool, service_url: str = '') -> str:
    """
    Append or replace body with JSON data based on service type.

    For JSON webhooks (json:// or jsons://): Returns pure JSON string for easy parsing
    For other services: Appends formatted JSON to existing body

    Args:
        body: Original notification body
        json_data: JSON string to append
        is_html: True for HTML format (email), False for Markdown (chat)
        service_url: Service URL to detect JSON webhooks

    Returns:
        Body with JSON data (appended or replaced depending on service type)
    """
    # For JSON webhooks: return pure JSON string (no markdown, no HTML)
    if _is_json_webhook(service_url):
        return json_data

    # For other services: append formatted JSON
    if is_html:
        # For email: use collapsible <details> section
        json_section = f'''
        <div style="margin-top: 20px; padding: 12px; background-color: #f8f9fa; border-radius: 4px;">
            <details>
                <summary style="cursor: pointer; font-weight: 600; color: #667eea;">
                    JSON Data (for automation)
                </summary>
                <pre style="margin-top: 10px; padding: 10px; background-color: #fff; border-radius: 4px; overflow-x: auto; font-size: 11px; font-family: 'Courier New', monospace;">{json_data}</pre>
            </details>
        </div>
    </div>
</body>
</html>'''
        # Replace the closing tags with JSON section + closing tags
        body = body.replace('</div>\n</body>\n</html>', json_section)
    else:
        # For chat: use markdown code block
        body += f"\n\n**JSON Data (for automation)**\n```json\n{json_data}\n```"

    return body


class NotificationService:
    """Service for sending notifications via Apprise."""

    @staticmethod
    async def send_backup_start(
        db: Session,
        repository_name: str,
        archive_name: str,
        source_directories: Optional[list] = None,
        expected_size: Optional[int] = None,
        job_name: Optional[str] = None
    ) -> None:
        """
        Send notification when backup starts.

        Args:
            db: Database session
            repository_name: Name of repository
            archive_name: Name of archive being created
            source_directories: List of source directories being backed up (optional)
            expected_size: Expected total size in bytes (optional)
            job_name: Name of the job/schedule (optional, for enhanced titles)
        """
        settings = db.query(NotificationSettings).filter(
            NotificationSettings.enabled == True,
            NotificationSettings.notify_on_backup_start == True
        ).all()

        if not settings:
            return

        # Look up repository details
        repo = _get_repository(db, repository_name)

        # Get repository type
        repo_type = _get_repository_type(repo)

        # Build content blocks
        content_blocks = [
            {'label': 'Archive', 'value': archive_name},
            {'label': 'Repository', 'value': f"{repo.name if repo else repository_name} ({repo_type})"},
        ]

        # Add path if repository found
        if repo:
            content_blocks.append({'label': 'Location', 'value': repo.path})

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

        # Create HTML body for email with professional badge
        html_title = f"{_get_status_badge('started', is_html=True)} Backup Started"
        html_body = _create_html_email(
            title=html_title,
            content_blocks=content_blocks,
            footer=f"Started at {timestamp_str}"
        )

        # Create markdown body for chat services with professional badge
        markdown_title = f"{_get_status_badge('started', is_html=False)} Backup Started"
        markdown_body = _create_markdown_message(
            title=markdown_title,
            content_blocks=content_blocks,
            footer=f"Started at {timestamp_str}"
        )

        # Send to all enabled services with this event trigger
        for setting in settings:
            # Check if this notification applies to this repository
            if not _notification_applies_to_repository(db, setting, repository_name):
                continue

            # Build title with optional job name and professional badge
            status_badge_text = _get_status_badge('started', is_html=False)

            title = f"{status_badge_text} Backup Started"
            if setting.include_job_name_in_title and job_name:
                title = f"{status_badge_text} Backup Started - {job_name}"
            if setting.title_prefix:
                title = f"{setting.title_prefix} {title}"

            # Prepare bodies (may add JSON if enabled)
            final_html_body = html_body
            final_markdown_body = markdown_body

            # Add JSON data if enabled
            if _should_include_json(setting):
                json_data = _build_json_data("backup_start", {
                    "repository_name": repo.name if repo else repository_name,
                    "repository_path": repo.path if repo else repository_name,
                    "archive_name": archive_name,
                    "job_name": job_name,
                    "source_directories": source_directories,
                    "expected_size": expected_size,
                    "started_at": start_time.isoformat()
                }, compact=_is_json_webhook(setting.service_url))
                final_html_body = _append_json_to_body(html_body, json_data, is_html=True, service_url=setting.service_url)
                final_markdown_body = _append_json_to_body(markdown_body, json_data, is_html=False, service_url=setting.service_url)

            await NotificationService._send_to_service(db, setting, title, final_html_body, final_markdown_body)

    @staticmethod
    async def send_backup_success(
        db: Session,
        repository_name: str,
        archive_name: str,
        stats: Optional[dict] = None,
        completion_time: Optional[datetime] = None,
        job_name: Optional[str] = None
    ) -> None:
        """
        Send notification for successful backup.

        Args:
            db: Database session
            repository_name: Name of repository
            archive_name: Name of created archive
            stats: Backup statistics (optional)
            completion_time: When the backup completed (optional, defaults to now)
            job_name: Name of the job/schedule (optional, for enhanced titles)
        """
        settings = db.query(NotificationSettings).filter(
            NotificationSettings.enabled == True,
            NotificationSettings.notify_on_backup_success == True
        ).all()

        if not settings:
            return

        # Look up repository details
        repo = _get_repository(db, repository_name)

        # Get repository type
        repo_type = _get_repository_type(repo)

        # Build content blocks for HTML email and markdown
        content_blocks = [
            {'label': 'Archive', 'value': archive_name},
            {'label': 'Repository', 'value': f"{repo.name if repo else repository_name} ({repo_type})"},
        ]

        # Add path if repository found
        if repo:
            content_blocks.append({'label': 'Location', 'value': repo.path})

        # Calculate derived metrics
        elapsed_time_str = None
        compression_ratio_str = None
        backup_speed_str = None

        if started_at and completion_time:
            elapsed_time_str = _format_duration(started_at, completion_time)

        if stats:
            original_size = stats.get('original_size', 0)
            compressed_size = stats.get('compressed_size', 0)

            if original_size and compressed_size:
                compression_ratio_str = _calculate_compression_ratio(original_size, compressed_size)

                if started_at and completion_time:
                    duration_seconds = (completion_time - started_at).total_seconds()
                    backup_speed_str = _calculate_backup_speed(original_size, duration_seconds)

        # Add performance metrics before stats
        if elapsed_time_str:
            content_blocks.append({'label': 'Duration', 'value': elapsed_time_str})
        if nfiles:
            content_blocks.append({'label': 'Files Processed', 'value': f"{nfiles:,}"})
        if backup_speed_str:
            content_blocks.append({'label': 'Average Speed', 'value': backup_speed_str})
        if compression_ratio_str:
            content_blocks.append({'label': 'Compression Ratio', 'value': compression_ratio_str})

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

        # Build footer with elapsed time if available
        footer = f"Completed at {timestamp_str}"
        if elapsed_time_str:
            footer = f"Completed at {timestamp_str} (took {elapsed_time_str})"

        # Create content blocks for markdown (including stats and performance metrics)
        markdown_blocks = [
            {'label': 'Archive', 'value': archive_name},
            {'label': 'Repository', 'value': f"{repo.name if repo else repository_name} ({repo_type})"},
        ]
        if repo:
            markdown_blocks.append({'label': 'Location', 'value': repo.path})
        if elapsed_time_str:
            markdown_blocks.append({'label': 'Duration', 'value': elapsed_time_str})
        if nfiles:
            markdown_blocks.append({'label': 'Files Processed', 'value': f"{nfiles:,}"})
        if backup_speed_str:
            markdown_blocks.append({'label': 'Average Speed', 'value': backup_speed_str})
        if compression_ratio_str:
            markdown_blocks.append({'label': 'Compression Ratio', 'value': compression_ratio_str})
        markdown_blocks.extend(stats_blocks)

        # Create HTML body for email with professional badge
        html_title = f"{_get_status_badge('success', is_html=True)} Backup Successful"
        html_body = _create_html_email(
            title=html_title,
            content_blocks=content_blocks,
            footer=footer
        )

        # Create Markdown body for chat services with professional badge
        markdown_title = f"{_get_status_badge('success', is_html=False)} Backup Successful"
        markdown_body = _create_markdown_message(
            title=markdown_title,
            content_blocks=markdown_blocks,
            footer=footer
        )

        for setting in settings:
            # Check if this notification applies to this repository
            if not _notification_applies_to_repository(db, setting, repository_name):
                continue

            # Build title with optional job name and professional badge
            status_badge_text = _get_status_badge('success', is_html=False)

            title = f"{status_badge_text} Backup Successful"
            if setting.include_job_name_in_title and job_name:
                title = f"{status_badge_text} Backup Successful - {job_name}"
            if setting.title_prefix:
                title = f"{setting.title_prefix} {title}"

            # Prepare bodies (may add JSON if enabled)
            final_html_body = html_body
            final_markdown_body = markdown_body

            # Add JSON data if enabled
            if _should_include_json(setting):
                json_data = _build_json_data("backup_success", {
                    "repository_name": repo.name if repo else repository_name,
                    "repository_path": repo.path if repo else repository_name,
                    "archive_name": archive_name,
                    "job_name": job_name,
                    "stats": stats,
                    "completed_at": completed_at.isoformat() if completed_at else None
                }, compact=_is_json_webhook(setting.service_url))
                final_html_body = _append_json_to_body(html_body, json_data, is_html=True, service_url=setting.service_url)
                final_markdown_body = _append_json_to_body(markdown_body, json_data, is_html=False, service_url=setting.service_url)

            await NotificationService._send_to_service(db, setting, title, final_html_body, final_markdown_body)

    @staticmethod
    async def send_backup_failure(
        db: Session,
        repository_name: str,
        error_message: str,
        job_id: Optional[int] = None,
        job_name: Optional[str] = None
    ) -> None:
        """
        Send notification for failed backup.

        Args:
            db: Database session
            repository_name: Name of repository
            error_message: Error description
            job_id: Backup job ID (optional)
            job_name: Name of the job/schedule (optional, for enhanced titles)
        """
        settings = db.query(NotificationSettings).filter(
            NotificationSettings.enabled == True,
            NotificationSettings.notify_on_backup_failure == True
        ).all()

        if not settings:
            return

        # Look up repository details
        repo = _get_repository(db, repository_name)

        # Get repository type
        repo_type = _get_repository_type(repo)

        # Build content blocks
        content_blocks = [
            {'label': 'Repository', 'value': f"{repo.name if repo else repository_name} ({repo_type})"},
        ]

        # Add path if repository found
        if repo:
            content_blocks.append({'label': 'Location', 'value': repo.path})

        if job_id:
            content_blocks.append({'label': 'Job ID', 'value': str(job_id)})

        # Add error box for HTML
        error_html = f'''
        <div class="error-box">
            <strong>Error Details:</strong>
            <pre>{error_message}</pre>
        </div>'''
        content_blocks.append({'html': error_html})

        # Capture failure time
        failure_time = datetime.now()

        # Create HTML body with professional badge
        html_title = f"{_get_status_badge('failed', is_html=True)} Backup Failed"
        html_body = _create_html_email(
            title=html_title,
            content_blocks=content_blocks,
            footer=f"Failed at {failure_time.strftime('%Y-%m-%d %H:%M:%S')}"
        )

        # Create markdown body with professional badge (without HTML error box)
        markdown_blocks = [
            {'label': 'Repository', 'value': f"{repo.name if repo else repository_name} ({repo_type})"},
        ]
        if repo:
            markdown_blocks.append({'label': 'Location', 'value': repo.path})
        if job_id:
            markdown_blocks.append({'label': 'Job ID', 'value': str(job_id)})
        markdown_blocks.append({'label': 'Error', 'value': f"```\n{error_message}\n```"})

        markdown_title = f"{_get_status_badge('failed', is_html=False)} Backup Failed"
        markdown_body = _create_markdown_message(
            title=markdown_title,
            content_blocks=markdown_blocks,
            footer=f"Failed at {failure_time.strftime('%Y-%m-%d %H:%M:%S')}"
        )

        for setting in settings:
            # Check if this notification applies to this repository
            if not _notification_applies_to_repository(db, setting, repository_name):
                continue

            # Build title with optional job name and professional badge
            status_badge_text = _get_status_badge('failed', is_html=False)

            title = f"{status_badge_text} Backup Failed"
            if setting.include_job_name_in_title and job_name:
                title = f"{status_badge_text} Backup Failed - {job_name}"
            if setting.title_prefix:
                title = f"{setting.title_prefix} {title}"

            # Prepare bodies (may add JSON if enabled)
            final_html_body = html_body
            final_markdown_body = markdown_body

            # Add JSON data if enabled
            if _should_include_json(setting):
                json_data = _build_json_data("backup_failure", {
                    "repository_name": repo.name if repo else repository_name,
                    "repository_path": repo.path if repo else repository_name,
                    "job_name": job_name,
                    "job_id": job_id,
                    "error_message": error_message,
                    "failed_at": failure_time.isoformat()
                }, compact=_is_json_webhook(setting.service_url))
                final_html_body = _append_json_to_body(html_body, json_data, is_html=True, service_url=setting.service_url)
                final_markdown_body = _append_json_to_body(markdown_body, json_data, is_html=False, service_url=setting.service_url)

            await NotificationService._send_to_service(db, setting, title, final_html_body, final_markdown_body)

    @staticmethod
    async def send_backup_warning(
        db: Session,
        repository_name: str,
        archive_name: str,
        warning_message: str,
        stats: Optional[dict] = None,
        completion_time: Optional[datetime] = None,
        job_name: Optional[str] = None,
        started_at: Optional[datetime] = None,
        nfiles: Optional[int] = None
    ) -> None:
        """
        Send notification for backup completed with warnings.

        Args:
            db: Database session
            repository_name: Name of repository
            archive_name: Name of created archive
            warning_message: Warning description
            stats: Backup statistics (optional)
            completion_time: When the backup completed (optional, defaults to now)
            job_name: Name of the job/schedule (optional, for enhanced titles)
            started_at: When the backup started (optional, for elapsed time calculation)
            nfiles: Number of files processed (optional)
        """
        settings = db.query(NotificationSettings).filter(
            NotificationSettings.enabled == True,
            NotificationSettings.notify_on_backup_success == True  # Use success setting for warnings
        ).all()

        if not settings:
            return

        # Look up repository details
        repo = _get_repository(db, repository_name)

        # Get repository type
        repo_type = _get_repository_type(repo)

        # Build content blocks for HTML email and markdown
        content_blocks = [
            {'label': 'Archive', 'value': archive_name},
            {'label': 'Repository', 'value': f"{repo.name if repo else repository_name} ({repo_type})"},
        ]

        # Add path if repository found
        if repo:
            content_blocks.append({'label': 'Location', 'value': repo.path})

        # Calculate derived metrics
        elapsed_time_str = None
        compression_ratio_str = None
        backup_speed_str = None

        if started_at and completion_time:
            elapsed_time_str = _format_duration(started_at, completion_time)

        if stats:
            original_size = stats.get('original_size', 0)
            compressed_size = stats.get('compressed_size', 0)

            if original_size and compressed_size:
                compression_ratio_str = _calculate_compression_ratio(original_size, compressed_size)

                if started_at and completion_time:
                    duration_seconds = (completion_time - started_at).total_seconds()
                    backup_speed_str = _calculate_backup_speed(original_size, duration_seconds)

        # Add performance metrics before stats
        if elapsed_time_str:
            content_blocks.append({'label': 'Duration', 'value': elapsed_time_str})
        if nfiles:
            content_blocks.append({'label': 'Files Processed', 'value': f"{nfiles:,}"})
        if backup_speed_str:
            content_blocks.append({'label': 'Average Speed', 'value': backup_speed_str})
        if compression_ratio_str:
            content_blocks.append({'label': 'Compression Ratio', 'value': compression_ratio_str})

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
                    <div class="stat-label">Compressed Size</div>
                    <div class="stat-value">{_format_bytes(stats['compressed_size'])}</div>
                </div>'''
                stats_blocks.append({'label': 'Compressed Size', 'value': _format_bytes(stats['compressed_size'])})

            if "deduplicated_size" in stats and stats["deduplicated_size"]:
                stats_html += f'''
                <div class="stat-card">
                    <div class="stat-label">Deduplicated Size</div>
                    <div class="stat-value">{_format_bytes(stats['deduplicated_size'])}</div>
                </div>'''
                stats_blocks.append({'label': 'Deduplicated Size', 'value': _format_bytes(stats['deduplicated_size'])})

            stats_html += '</div>'
            content_blocks.append({'html': stats_html})

        # Add warning box for HTML
        warning_html = f'''
        <div class="warning-box" style="background-color: #fff3cd; border-left: 4px solid #ffc107; padding: 12px; margin: 10px 0; border-radius: 4px;">
            <strong style="color: #856404;">Warning Details:</strong>
            <pre style="margin: 8px 0 0 0; color: #856404;">{warning_message}</pre>
        </div>'''
        content_blocks.append({'html': warning_html})

        # Capture completion time
        completed_at = completion_time or datetime.now()

        # Build footer with elapsed time if available
        footer = f"Completed at {completed_at.strftime('%Y-%m-%d %H:%M:%S')}"
        if elapsed_time_str:
            footer = f"Completed at {completed_at.strftime('%Y-%m-%d %H:%M:%S')} (took {elapsed_time_str})"

        # Create HTML body with professional badge
        html_title = f"{_get_status_badge('warning', is_html=True)} Backup Completed with Warnings"
        html_body = _create_html_email(
            title=html_title,
            content_blocks=content_blocks,
            footer=footer
        )

        # Create markdown body with professional badge
        markdown_blocks = [
            {'label': 'Archive', 'value': archive_name},
            {'label': 'Repository', 'value': f"{repo.name if repo else repository_name} ({repo_type})"},
        ]
        if repo:
            markdown_blocks.append({'label': 'Location', 'value': repo.path})
        if elapsed_time_str:
            markdown_blocks.append({'label': 'Duration', 'value': elapsed_time_str})
        if nfiles:
            markdown_blocks.append({'label': 'Files Processed', 'value': f"{nfiles:,}"})
        if backup_speed_str:
            markdown_blocks.append({'label': 'Average Speed', 'value': backup_speed_str})
        if compression_ratio_str:
            markdown_blocks.append({'label': 'Compression Ratio', 'value': compression_ratio_str})
        markdown_blocks.extend(stats_blocks)
        markdown_blocks.append({'label': 'Warning', 'value': f"```\n{warning_message}\n```"})

        markdown_title = f"{_get_status_badge('warning', is_html=False)} Backup Completed with Warnings"
        markdown_body = _create_markdown_message(
            title=markdown_title,
            content_blocks=markdown_blocks,
            footer=footer
        )

        for setting in settings:
            # Check if this notification applies to this repository
            if not _notification_applies_to_repository(db, setting, repository_name):
                continue

            # Build title with optional job name and professional badge
            status_badge_text = _get_status_badge('warning', is_html=False)

            title = f"{status_badge_text} Backup Completed with Warnings"
            if setting.include_job_name_in_title and job_name:
                title = f"{status_badge_text} Backup Completed with Warnings - {job_name}"
            if setting.title_prefix:
                title = f"{setting.title_prefix} {title}"

            # Prepare bodies (may add JSON if enabled)
            final_html_body = html_body
            final_markdown_body = markdown_body

            # Add JSON data if enabled
            if _should_include_json(setting):
                json_data = _build_json_data("backup_warning", {
                    "repository_name": repo.name if repo else repository_name,
                    "repository_path": repo.path if repo else repository_name,
                    "archive_name": archive_name,
                    "job_name": job_name,
                    "warning_message": warning_message,
                    "stats": stats,
                    "completed_at": completed_at.isoformat()
                }, compact=_is_json_webhook(setting.service_url))
                final_html_body = _append_json_to_body(html_body, json_data, is_html=True, service_url=setting.service_url)
                final_markdown_body = _append_json_to_body(markdown_body, json_data, is_html=False, service_url=setting.service_url)

            await NotificationService._send_to_service(db, setting, title, final_html_body, final_markdown_body)

    @staticmethod
    async def send_restore_success(
        db: Session,
        repository_name: str,
        archive_name: str,
        target_path: str,
        completion_time: Optional[datetime] = None,
        job_name: Optional[str] = None
    ) -> None:
        """
        Send notification for successful restore.

        Args:
            db: Database session
            repository_name: Name of repository
            archive_name: Name of restored archive
            target_path: Restore destination
            completion_time: When the restore completed (optional, defaults to now)
            job_name: Name of the job/schedule (optional, for enhanced titles)
        """
        settings = db.query(NotificationSettings).filter(
            NotificationSettings.enabled == True,
            NotificationSettings.notify_on_restore_success == True
        ).all()

        if not settings:
            return

        # Look up repository details
        repo = _get_repository(db, repository_name)

        # Get repository type
        repo_type = _get_repository_type(repo)

        # Build content blocks
        content_blocks = [
            {'label': 'Archive', 'value': archive_name},
            {'label': 'Repository', 'value': f"{repo.name if repo else repository_name} ({repo_type})"},
        ]
        # Add path if repository found
        if repo:
            content_blocks.append({'label': 'Location', 'value': repo.path})

        content_blocks.append({'label': 'Destination', 'value': target_path})

        # Use provided completion time or current time as fallback
        completed_at = completion_time or datetime.now()
        timestamp_str = completed_at.strftime('%Y-%m-%d %H:%M:%S')

        html_title = f"{_get_status_badge('success', is_html=True)} Restore Successful"
        html_body = _create_html_email(
            title=html_title,
            content_blocks=content_blocks,
            footer=f"Completed at {timestamp_str}"
        )

        markdown_title = f"{_get_status_badge('success', is_html=False)} Restore Successful"
        markdown_body = _create_markdown_message(
            title=markdown_title,
            content_blocks=content_blocks,
            footer=f"Completed at {timestamp_str}"
        )

        for setting in settings:
            # Check if this notification applies to this repository
            if not _notification_applies_to_repository(db, setting, repository_name):
                continue

            # Build title with optional job name and professional badge
            status_badge_text = _get_status_badge('success', is_html=False)

            title = f"{status_badge_text} Restore Successful"
            if setting.include_job_name_in_title and job_name:
                title = f"{status_badge_text} Restore Successful - {job_name}"
            if setting.title_prefix:
                title = f"{setting.title_prefix} {title}"

            # Prepare bodies (may add JSON if enabled)
            final_html_body = html_body
            final_markdown_body = markdown_body

            # Add JSON data if enabled
            if _should_include_json(setting):
                json_data = _build_json_data("restore_success", {
                    "repository_name": repo.name if repo else repository_name,
                    "repository_path": repo.path if repo else repository_name,
                    "archive_name": archive_name,
                    "job_name": job_name,
                    "target_path": target_path,
                    "completed_at": completed_at.isoformat()
                }, compact=_is_json_webhook(setting.service_url))
                final_html_body = _append_json_to_body(html_body, json_data, is_html=True, service_url=setting.service_url)
                final_markdown_body = _append_json_to_body(markdown_body, json_data, is_html=False, service_url=setting.service_url)

            await NotificationService._send_to_service(db, setting, title, final_html_body, final_markdown_body)

    @staticmethod
    async def send_restore_failure(
        db: Session,
        repository_name: str,
        archive_name: str,
        error_message: str,
        job_name: Optional[str] = None
    ) -> None:
        """
        Send notification for failed restore.

        Args:
            db: Database session
            repository_name: Name of repository
            archive_name: Name of archive
            error_message: Error description
            job_name: Name of the job/schedule (optional, for enhanced titles)
        """
        settings = db.query(NotificationSettings).filter(
            NotificationSettings.enabled == True,
            NotificationSettings.notify_on_restore_failure == True
        ).all()

        if not settings:
            return

        # Look up repository details
        repo = _get_repository(db, repository_name)

        # Get repository type
        repo_type = _get_repository_type(repo)

        # Build content blocks
        content_blocks = [
            {'label': 'Archive', 'value': archive_name},
            {'label': 'Repository', 'value': f"{repo.name if repo else repository_name} ({repo_type})"},
        ]

        # Add path if repository found
        if repo:
            content_blocks.append({'label': 'Location', 'value': repo.path})

        error_html = f'''
        <div class="error-box">
            <strong>Error Details:</strong>
            <pre>{error_message}</pre>
        </div>'''
        content_blocks.append({'html': error_html})

        html_title = f"{_get_status_badge('failed', is_html=True)} Restore Failed"
        html_body = _create_html_email(
            title=html_title,
            content_blocks=content_blocks,
            footer=f"Failed at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )

        # Create markdown body
        markdown_blocks = [
            {'label': 'Archive', 'value': archive_name},
            {'label': 'Repository', 'value': f"{repo.name if repo else repository_name} ({repo_type})"},
        ]
        if repo:
            markdown_blocks.append({'label': 'Location', 'value': repo.path})

        markdown_blocks.append({'label': 'Error', 'value': f"```\n{error_message}\n```"})

        markdown_title = f"{_get_status_badge('failed', is_html=False)} Restore Failed"
        markdown_body = _create_markdown_message(
            title=markdown_title,
            content_blocks=markdown_blocks,
            footer=f"Failed at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )

        # Capture failure time for JSON
        failure_time = datetime.now()

        for setting in settings:
            # Check if this notification applies to this repository
            if not _notification_applies_to_repository(db, setting, repository_name):
                continue

            # Build title with optional job name and professional badge
            status_badge_text = _get_status_badge('failed', is_html=False)

            title = f"{status_badge_text} Restore Failed"
            if setting.include_job_name_in_title and job_name:
                title = f"{status_badge_text} Restore Failed - {job_name}"
            if setting.title_prefix:
                title = f"{setting.title_prefix} {title}"

            # Prepare bodies (may add JSON if enabled)
            final_html_body = html_body
            final_markdown_body = markdown_body

            # Add JSON data if enabled
            if _should_include_json(setting):
                json_data = _build_json_data("restore_failure", {
                    "repository_name": repo.name if repo else repository_name,
                    "repository_path": repo.path if repo else repository_name,
                    "archive_name": archive_name,
                    "job_name": job_name,
                    "error_message": error_message,
                    "failed_at": failure_time.isoformat()
                }, compact=_is_json_webhook(setting.service_url))
                final_html_body = _append_json_to_body(html_body, json_data, is_html=True, service_url=setting.service_url)
                final_markdown_body = _append_json_to_body(markdown_body, json_data, is_html=False, service_url=setting.service_url)

            await NotificationService._send_to_service(db, setting, title, final_html_body, final_markdown_body)

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

        # Look up repository details
        repo = _get_repository(db, repository_name)

        # Build content blocks
        content_blocks = [
            {'label': 'Schedule', 'value': schedule_name},
            {'label': 'Repository', 'value': repo.name if repo else repository_name},
        ]
        # Add path if repository found
        if repo:
            content_blocks.append({'label': 'Location', 'value': repo.path})

        error_html = f'''
        <div class="error-box">
            <strong>Error Details:</strong>
            <pre>{error_message}</pre>
        </div>'''
        content_blocks.append({'html': error_html})

        html_title = f"{_get_status_badge('failed', is_html=True)} Scheduled Backup Failed"
        html_body = _create_html_email(
            title=html_title,
            content_blocks=content_blocks,
            footer=f"Failed at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )

        # Create markdown body
        markdown_blocks = [
            {'label': 'Schedule', 'value': schedule_name},
            {'label': 'Repository', 'value': repo.name if repo else repository_name},
        ]
        if repo:
            markdown_blocks.append({'label': 'Location', 'value': repo.path})
            
        markdown_blocks.append({'label': 'Error', 'value': f"```\n{error_message}\n```"})

        markdown_title = f"{_get_status_badge('failed', is_html=False)} Scheduled Backup Failed"
        markdown_body = _create_markdown_message(
            title=markdown_title,
            content_blocks=markdown_blocks,
            footer=f"Failed at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )

        # Capture failure time for JSON
        failure_time = datetime.now()

        for setting in settings:
            # Check if this notification applies to this repository
            if not _notification_applies_to_repository(db, setting, repository_name):
                continue

            # Build title with optional schedule name and professional badge
            status_badge_text = _get_status_badge('failed', is_html=False)

            title = f"{status_badge_text} Scheduled Backup Failed"
            if setting.include_job_name_in_title and schedule_name:
                title = f"{status_badge_text} Scheduled Backup Failed - {schedule_name}"
            if setting.title_prefix:
                title = f"{setting.title_prefix} {title}"

            # Prepare bodies (may add JSON if enabled)
            final_html_body = html_body
            final_markdown_body = markdown_body

            # Add JSON data if enabled
            if _should_include_json(setting):
                json_data = _build_json_data("schedule_failure", {
                    "schedule_name": schedule_name,
                    "repository_name": repo.name if repo else repository_name,
                    "repository_path": repo.path if repo else repository_name,
                    "error_message": error_message,
                    "failed_at": failure_time.isoformat()
                }, compact=_is_json_webhook(setting.service_url))
                final_html_body = _append_json_to_body(html_body, json_data, is_html=True, service_url=setting.service_url)
                final_markdown_body = _append_json_to_body(markdown_body, json_data, is_html=False, service_url=setting.service_url)

            await NotificationService._send_to_service(db, setting, title, final_html_body, final_markdown_body)

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

            # Use longer timeout for slow services like Signal (60 seconds)
            # Temporarily set socket timeout since Apprise plugins use it for HTTP connections
            old_timeout = socket.getdefaulttimeout()
            socket.setdefaulttimeout(60)
            try:
                success = apobj.notify(
                    title="🔔 Borg UI Test Notification",
                    body="This is a test notification from Borg Web UI. If you received this, your notification service is configured correctly!"
                )
            finally:
                socket.setdefaulttimeout(old_timeout)

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
            # Use longer timeout (60s) for slow services like Signal
            # Temporarily set socket timeout since Apprise plugins use it for HTTP connections
            old_timeout = socket.getdefaulttimeout()
            socket.setdefaulttimeout(60)
            try:
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
            finally:
                socket.setdefaulttimeout(old_timeout)

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

    @staticmethod
    async def send_check_completion(
        db: Session,
        repository_name: str,
        repository_path: str,
        status: str,  # "completed" or "failed"
        duration_seconds: Optional[int] = None,
        error_message: Optional[str] = None,
        check_type: str = "manual",  # "manual" or "scheduled"
        job_name: Optional[str] = None
    ) -> None:
        """
        Send notification for check completion (success or failure).

        Args:
            db: Database session
            repository_name: Name of repository
            repository_path: Path to repository
            status: "completed" or "failed"
            duration_seconds: How long check took
            error_message: Error message if failed
            check_type: "manual" or "scheduled"
            job_name: Name of the job/schedule (optional, for enhanced titles)
        """
        # Determine which settings to use
        if status == "completed":
            settings = db.query(NotificationSettings).filter(
                NotificationSettings.enabled == True,
                NotificationSettings.notify_on_check_success == True
            ).all()
        else:  # failed
            settings = db.query(NotificationSettings).filter(
                NotificationSettings.enabled == True,
                NotificationSettings.notify_on_check_failure == True
            ).all()

        if not settings:
            return

        # Build content blocks
        content_blocks = [
            {'label': 'Repository', 'value': repository_name},
            {'label': 'Path', 'value': repository_path},
            {'label': 'Type', 'value': check_type.capitalize()},
        ]

        # Add duration if provided
        if duration_seconds is not None:
            if duration_seconds < 60:
                duration_str = f"{duration_seconds}s"
            elif duration_seconds < 3600:
                duration_str = f"{duration_seconds // 60}m {duration_seconds % 60}s"
            else:
                hours = duration_seconds // 3600
                mins = (duration_seconds % 3600) // 60
                duration_str = f"{hours}h {mins}m"
            content_blocks.append({'label': 'Duration', 'value': duration_str})

        # Add error message if failed
        if status == "failed" and error_message:
            # Truncate long error messages
            error_display = error_message if len(error_message) <= 200 else error_message[:200] + "..."
            content_blocks.append({'label': 'Error', 'value': error_display})

        # Create timestamp
        completion_time = datetime.now()
        timestamp_str = completion_time.strftime('%Y-%m-%d %H:%M:%S')

        # Choose title and badge based on status
        if status == "completed":
            badge_type = "success"
            title_text = "Check Completed"
        else:
            badge_type = "failed"
            title_text = "Check Failed"

        # Create HTML body for email with professional badge
        html_title = f"{_get_status_badge(badge_type, is_html=True)} Repository {title_text}"
        html_body = _create_html_email(
            title=html_title,
            content_blocks=content_blocks,
            footer=f"Completed at {timestamp_str}"
        )

        # Create markdown body for chat services with professional badge
        markdown_title = f"{_get_status_badge(badge_type, is_html=False)} Repository {title_text}"
        markdown_body = _create_markdown_message(
            title=markdown_title,
            content_blocks=content_blocks,
            footer=f"Completed at {timestamp_str}"
        )

        # Send to all enabled services with this event trigger
        for setting in settings:
            # Check if this notification applies to this repository
            if not _notification_applies_to_repository(db, setting, repository_name):
                continue

            # Build title with optional job name and professional badge
            status_badge_text = _get_status_badge(badge_type, is_html=False)

            title = f"{status_badge_text} Repository {title_text}"
            if setting.include_job_name_in_title and job_name:
                title = f"{status_badge_text} Repository {title_text} - {job_name}"
            if setting.title_prefix:
                title = f"{setting.title_prefix} {title}"

            # Prepare bodies (may add JSON if enabled)
            final_html_body = html_body
            final_markdown_body = markdown_body

            # Add JSON data if enabled
            if _should_include_json(setting):
                event_type = f"check_{status}"  # "check_completed" or "check_failed"
                json_data = _build_json_data(event_type, {
                    "repository_name": repository_name,
                    "repository_path": repository_path,
                    "job_name": job_name,
                    "check_type": check_type,
                    "status": status,
                    "duration_seconds": duration_seconds,
                    "error_message": error_message if status == "failed" else None,
                    "completed_at": completion_time.isoformat()
                }, compact=_is_json_webhook(setting.service_url))
                final_html_body = _append_json_to_body(html_body, json_data, is_html=True, service_url=setting.service_url)
                final_markdown_body = _append_json_to_body(markdown_body, json_data, is_html=False, service_url=setting.service_url)

            await NotificationService._send_to_service(db, setting, title, final_html_body, final_markdown_body)


# Global instance
notification_service = NotificationService()
