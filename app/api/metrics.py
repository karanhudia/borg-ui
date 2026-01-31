"""
Prometheus metrics endpoint for borg-ui

Exports metrics in Prometheus text format for monitoring and alerting.
Accessible at /metrics (no authentication required for Prometheus scraping).
"""

from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timezone
import structlog

from app.database.database import get_db
from app.database.models import (
    Repository, BackupJob, RestoreJob, CheckJob, CompactJob, PruneJob,
    ScheduledJob, DeleteArchiveJob
)

logger = structlog.get_logger()
router = APIRouter(tags=["metrics"])


def parse_size_string(size_str: str) -> int:
    """Convert size string like '1.5 GB' to bytes"""
    if not size_str:
        return 0

    size_str = size_str.strip()
    # Check longer units first to avoid matching 'B' in 'GB'
    units = [
        ('PB', 1024 ** 5),
        ('TB', 1024 ** 4),
        ('GB', 1024 ** 3),
        ('MB', 1024 ** 2),
        ('KB', 1024),
        ('B', 1),
    ]

    try:
        for unit, multiplier in units:
            if unit in size_str:
                number = float(size_str.replace(unit, '').strip())
                return int(number * multiplier)
        return int(float(size_str))
    except:
        return 0


def timestamp_to_unix(dt: datetime) -> int:
    """Convert datetime to Unix timestamp"""
    if not dt:
        return 0
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


@router.get("/metrics", response_class=PlainTextResponse)
async def get_metrics(db: Session = Depends(get_db)):
    """
    Prometheus metrics endpoint

    Returns metrics in Prometheus text format for scraping.
    No authentication required to allow Prometheus to scrape freely.
    """
    lines = []

    # Header
    lines.append("# Prometheus metrics for borg-ui")
    lines.append(f"# Generated at {datetime.now(timezone.utc).isoformat()}")
    lines.append("")

    try:
        # ===== Repository Metrics =====
        repositories = db.query(Repository).all()

        lines.append("# HELP borg_repository_info Repository information (always 1)")
        lines.append("# TYPE borg_repository_info gauge")
        for repo in repositories:
            labels = (
                f'repository="{repo.name}",'
                f'path="{repo.path}",'
                f'type="{repo.repository_type}",'
                f'mode="{repo.mode}"'
            )
            lines.append(f"borg_repository_info{{{labels}}} 1")
        lines.append("")

        lines.append("# HELP borg_repository_size_bytes Repository total size in bytes")
        lines.append("# TYPE borg_repository_size_bytes gauge")
        for repo in repositories:
            size_bytes = parse_size_string(repo.total_size or "0")
            lines.append(f'borg_repository_size_bytes{{repository="{repo.name}"}} {size_bytes}')
        lines.append("")

        lines.append("# HELP borg_repository_archive_count Number of archives in repository")
        lines.append("# TYPE borg_repository_archive_count gauge")
        for repo in repositories:
            lines.append(f'borg_repository_archive_count{{repository="{repo.name}"}} {repo.archive_count or 0}')
        lines.append("")

        lines.append("# HELP borg_repository_last_backup_timestamp Unix timestamp of last backup")
        lines.append("# TYPE borg_repository_last_backup_timestamp gauge")
        for repo in repositories:
            timestamp = timestamp_to_unix(repo.last_backup)
            lines.append(f'borg_repository_last_backup_timestamp{{repository="{repo.name}"}} {timestamp}')
        lines.append("")

        lines.append("# HELP borg_repository_last_check_timestamp Unix timestamp of last check")
        lines.append("# TYPE borg_repository_last_check_timestamp gauge")
        for repo in repositories:
            timestamp = timestamp_to_unix(repo.last_check)
            lines.append(f'borg_repository_last_check_timestamp{{repository="{repo.name}"}} {timestamp}')
        lines.append("")

        lines.append("# HELP borg_repository_last_compact_timestamp Unix timestamp of last compact")
        lines.append("# TYPE borg_repository_last_compact_timestamp gauge")
        for repo in repositories:
            timestamp = timestamp_to_unix(repo.last_compact)
            lines.append(f'borg_repository_last_compact_timestamp{{repository="{repo.name}"}} {timestamp}')
        lines.append("")

        # ===== Backup Job Metrics =====
        lines.append("# HELP borg_backup_jobs_total Total number of backup jobs by status")
        lines.append("# TYPE borg_backup_jobs_total gauge")

        # Create a mapping of repo path to name for consistent labeling
        repo_path_to_name = {repo.path: repo.name for repo in repositories}

        backup_status_counts = db.query(
            BackupJob.repository,
            BackupJob.status,
            func.count(BackupJob.id).label('count')
        ).group_by(BackupJob.repository, BackupJob.status).all()

        # Separate active repository jobs from orphaned jobs
        orphaned_jobs = []
        for repo_path, status, count in backup_status_counts:
            if repo_path in repo_path_to_name:
                # Active repository - use repository name
                repo_name = repo_path_to_name[repo_path]
                lines.append(f'borg_backup_jobs_total{{repository="{repo_name}",status="{status}"}} {count}')
            else:
                # Orphaned job - repository no longer exists
                orphaned_jobs.append((repo_path, status, count))
        lines.append("")

        # Show orphaned jobs separately for visibility
        lines.append("# HELP borg_backup_orphaned_jobs_total Backup jobs for deleted/renamed repositories")
        lines.append("# TYPE borg_backup_orphaned_jobs_total gauge")
        for repo_path, status, count in orphaned_jobs:
            lines.append(f'borg_backup_orphaned_jobs_total{{repository_path="{repo_path}",status="{status}"}} {count}')
        lines.append("")

        lines.append("# HELP borg_backup_last_job_success Last backup job success (1=success, 0=failure)")
        lines.append("# TYPE borg_backup_last_job_success gauge")

        for repo in repositories:
            last_job = db.query(BackupJob).filter(
                BackupJob.repository == repo.path
            ).order_by(BackupJob.created_at.desc()).first()

            if last_job:
                success = 1 if last_job.status in ("completed", "completed_with_warnings") else 0
                lines.append(f'borg_backup_last_job_success{{repository="{repo.name}"}} {success}')
        lines.append("")

        lines.append("# HELP borg_backup_last_duration_seconds Duration of last backup job in seconds")
        lines.append("# TYPE borg_backup_last_duration_seconds gauge")

        for repo in repositories:
            last_job = db.query(BackupJob).filter(
                BackupJob.repository == repo.path,
                BackupJob.started_at.isnot(None),
                BackupJob.completed_at.isnot(None)
            ).order_by(BackupJob.completed_at.desc()).first()

            if last_job and last_job.started_at and last_job.completed_at:
                duration = (last_job.completed_at - last_job.started_at).total_seconds()
                lines.append(f'borg_backup_last_duration_seconds{{repository="{repo.name}"}} {duration:.2f}')
        lines.append("")

        lines.append("# HELP borg_backup_last_original_size_bytes Original size of last backup in bytes")
        lines.append("# TYPE borg_backup_last_original_size_bytes gauge")

        for repo in repositories:
            last_job = db.query(BackupJob).filter(
                BackupJob.repository == repo.path,
                BackupJob.status.in_(["completed", "completed_with_warnings"])
            ).order_by(BackupJob.completed_at.desc()).first()

            if last_job:
                lines.append(f'borg_backup_last_original_size_bytes{{repository="{repo.name}"}} {last_job.original_size or 0}')
        lines.append("")

        lines.append("# HELP borg_backup_last_deduplicated_size_bytes Deduplicated size of last backup in bytes")
        lines.append("# TYPE borg_backup_last_deduplicated_size_bytes gauge")

        for repo in repositories:
            last_job = db.query(BackupJob).filter(
                BackupJob.repository == repo.path,
                BackupJob.status.in_(["completed", "completed_with_warnings"])
            ).order_by(BackupJob.completed_at.desc()).first()

            if last_job:
                lines.append(f'borg_backup_last_deduplicated_size_bytes{{repository="{repo.name}"}} {last_job.deduplicated_size or 0}')
        lines.append("")

        # ===== Restore Job Metrics =====
        lines.append("# HELP borg_restore_jobs_total Total number of restore jobs by status")
        lines.append("# TYPE borg_restore_jobs_total gauge")

        restore_status_counts = db.query(
            RestoreJob.status,
            func.count(RestoreJob.id).label('count')
        ).group_by(RestoreJob.status).all()

        for status, count in restore_status_counts:
            lines.append(f'borg_restore_jobs_total{{status="{status}"}} {count}')
        lines.append("")

        # ===== Check Job Metrics =====
        lines.append("# HELP borg_check_jobs_total Total number of check jobs by status")
        lines.append("# TYPE borg_check_jobs_total gauge")

        check_status_counts = db.query(
            Repository.name,
            CheckJob.status,
            func.count(CheckJob.id).label('count')
        ).join(Repository, CheckJob.repository_id == Repository.id
        ).group_by(Repository.name, CheckJob.status).all()

        for repo_name, status, count in check_status_counts:
            lines.append(f'borg_check_jobs_total{{repository="{repo_name}",status="{status}"}} {count}')
        lines.append("")

        lines.append("# HELP borg_check_last_duration_seconds Duration of last check job in seconds")
        lines.append("# TYPE borg_check_last_duration_seconds gauge")

        for repo in repositories:
            last_job = db.query(CheckJob).filter(
                CheckJob.repository_id == repo.id,
                CheckJob.started_at.isnot(None),
                CheckJob.completed_at.isnot(None)
            ).order_by(CheckJob.completed_at.desc()).first()

            if last_job and last_job.started_at and last_job.completed_at:
                duration = (last_job.completed_at - last_job.started_at).total_seconds()
                lines.append(f'borg_check_last_duration_seconds{{repository="{repo.name}"}} {duration:.2f}')
        lines.append("")

        # ===== Compact Job Metrics =====
        lines.append("# HELP borg_compact_jobs_total Total number of compact jobs by status")
        lines.append("# TYPE borg_compact_jobs_total gauge")

        compact_status_counts = db.query(
            Repository.name,
            CompactJob.status,
            func.count(CompactJob.id).label('count')
        ).join(Repository, CompactJob.repository_id == Repository.id
        ).group_by(Repository.name, CompactJob.status).all()

        for repo_name, status, count in compact_status_counts:
            lines.append(f'borg_compact_jobs_total{{repository="{repo_name}",status="{status}"}} {count}')
        lines.append("")

        lines.append("# HELP borg_compact_last_duration_seconds Duration of last compact job in seconds")
        lines.append("# TYPE borg_compact_last_duration_seconds gauge")

        for repo in repositories:
            last_job = db.query(CompactJob).filter(
                CompactJob.repository_id == repo.id,
                CompactJob.started_at.isnot(None),
                CompactJob.completed_at.isnot(None)
            ).order_by(CompactJob.completed_at.desc()).first()

            if last_job and last_job.started_at and last_job.completed_at:
                duration = (last_job.completed_at - last_job.started_at).total_seconds()
                lines.append(f'borg_compact_last_duration_seconds{{repository="{repo.name}"}} {duration:.2f}')
        lines.append("")

        # ===== Prune Job Metrics =====
        lines.append("# HELP borg_prune_jobs_total Total number of prune jobs by status")
        lines.append("# TYPE borg_prune_jobs_total gauge")

        prune_status_counts = db.query(
            Repository.name,
            PruneJob.status,
            func.count(PruneJob.id).label('count')
        ).join(Repository, PruneJob.repository_id == Repository.id
        ).group_by(Repository.name, PruneJob.status).all()

        for repo_name, status, count in prune_status_counts:
            lines.append(f'borg_prune_jobs_total{{repository="{repo_name}",status="{status}"}} {count}')
        lines.append("")

        # ===== System Metrics =====
        lines.append("# HELP borg_ui_repositories_total Total number of repositories")
        lines.append("# TYPE borg_ui_repositories_total gauge")
        repo_count = db.query(func.count(Repository.id)).scalar()
        lines.append(f"borg_ui_repositories_total {repo_count}")
        lines.append("")

        lines.append("# HELP borg_ui_scheduled_jobs_total Total number of scheduled jobs")
        lines.append("# TYPE borg_ui_scheduled_jobs_total gauge")
        scheduled_count = db.query(func.count(ScheduledJob.id)).scalar()
        lines.append(f"borg_ui_scheduled_jobs_total {scheduled_count}")
        lines.append("")

        lines.append("# HELP borg_ui_scheduled_jobs_enabled Number of enabled scheduled jobs")
        lines.append("# TYPE borg_ui_scheduled_jobs_enabled gauge")
        enabled_count = db.query(func.count(ScheduledJob.id)).filter(ScheduledJob.enabled == True).scalar()
        lines.append(f"borg_ui_scheduled_jobs_enabled {enabled_count}")
        lines.append("")

        lines.append("# HELP borg_ui_active_jobs Number of currently running jobs by type")
        lines.append("# TYPE borg_ui_active_jobs gauge")

        active_backups = db.query(func.count(BackupJob.id)).filter(
            BackupJob.status.in_(["pending", "running"])
        ).scalar()
        lines.append(f'borg_ui_active_jobs{{type="backup"}} {active_backups}')

        active_restores = db.query(func.count(RestoreJob.id)).filter(
            RestoreJob.status.in_(["pending", "running"])
        ).scalar()
        lines.append(f'borg_ui_active_jobs{{type="restore"}} {active_restores}')

        active_checks = db.query(func.count(CheckJob.id)).filter(
            CheckJob.status.in_(["pending", "running"])
        ).scalar()
        lines.append(f'borg_ui_active_jobs{{type="check"}} {active_checks}')

        active_compacts = db.query(func.count(CompactJob.id)).filter(
            CompactJob.status.in_(["pending", "running"])
        ).scalar()
        lines.append(f'borg_ui_active_jobs{{type="compact"}} {active_compacts}')

        active_prunes = db.query(func.count(PruneJob.id)).filter(
            PruneJob.status.in_(["pending", "running"])
        ).scalar()
        lines.append(f'borg_ui_active_jobs{{type="prune"}} {active_prunes}')

        lines.append("")

        logger.info("Metrics endpoint accessed", metrics_count=len([l for l in lines if not l.startswith("#") and l]))

    except Exception as e:
        logger.error("Failed to generate metrics", error=str(e))
        lines.append(f"# ERROR: {str(e)}")

    return "\n".join(lines)
