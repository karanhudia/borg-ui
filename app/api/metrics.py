"""
Prometheus metrics endpoint for borg-ui

Exports metrics in Prometheus text format for monitoring and alerting.
Accessible at /metrics when enabled in system settings. Token authentication is optional.
"""

from typing import Optional, Tuple

from fastapi import APIRouter, Depends, Header, HTTPException, status as http_status
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timezone
import structlog

from app.database.database import get_db
from app.database.models import (
    Repository,
    Operation,
    SystemSettings,
    ScheduledJob,
)
from app.services.operations.backup_facade import latest_backup_job_for_repository
from app.services.operations.job_facade import legacy_status
from app.services.storage_usage import stored_size_bytes
from app.utils.datetime_utils import serialize_datetime

logger = structlog.get_logger()

# The Prometheus families below predate `operations` and their consumers parse
# the legacy status words, so `queued` is reported as `pending` (the same
# translation the HTTP routes make).
_ACTIVE_STATUSES = ("queued", "running")


def _counts_by_status(db: Session, kind: str) -> list[tuple[str, int]]:
    """Operation counts of one kind per legacy status word."""
    counts: dict[str, int] = {}
    rows = (
        db.query(Operation.status, func.count(Operation.id))
        .filter(Operation.kind == kind)
        .group_by(Operation.status)
        .all()
    )
    for status, count in rows:
        word = legacy_status(status)
        counts[word] = counts.get(word, 0) + count
    return sorted(counts.items())


def _counts_by_repository(db: Session, kind: str) -> list[tuple[str, str, int]]:
    """Operation counts of one kind per repository name and legacy status."""
    counts: dict[tuple[str, str], int] = {}
    rows = (
        db.query(Repository.name, Operation.status, func.count(Operation.id))
        .join(Repository, Operation.repository_id == Repository.id)
        .filter(Operation.kind == kind)
        .group_by(Repository.name, Operation.status)
        .all()
    )
    for repo_name, status, count in rows:
        key = (repo_name, legacy_status(status))
        counts[key] = counts.get(key, 0) + count
    return [(name, status, count) for (name, status), count in sorted(counts.items())]


def _last_finished(db: Session, kind: str, repository_id: int):
    """The newest operation of one kind that both started and finished."""
    return (
        db.query(Operation)
        .filter(
            Operation.kind == kind,
            Operation.repository_id == repository_id,
            Operation.started_at.isnot(None),
            Operation.completed_at.isnot(None),
        )
        .order_by(Operation.completed_at.desc())
        .first()
    )


def _active_count(db: Session, kind: str) -> int:
    return (
        db.query(func.count(Operation.id))
        .filter(Operation.kind == kind, Operation.status.in_(_ACTIVE_STATUSES))
        .scalar()
    )


router = APIRouter(tags=["metrics"])


def _resolve_metrics_settings(db: Session) -> Tuple[bool, bool, Optional[str]]:
    settings = db.query(SystemSettings).first()
    if settings is None:
        return False, False, None
    return (
        settings.metrics_enabled if settings.metrics_enabled is not None else False,
        settings.metrics_require_auth
        if settings.metrics_require_auth is not None
        else False,
        settings.metrics_token,
    )


def _extract_metrics_token(
    x_borg_metrics_token: Optional[str],
    authorization: Optional[str],
) -> Optional[str]:
    if x_borg_metrics_token:
        return x_borg_metrics_token
    if authorization and authorization.startswith("Bearer "):
        return authorization.split(" ", 1)[1]
    return None


def timestamp_to_unix(dt: datetime) -> int:
    """Convert datetime to Unix timestamp"""
    if not dt:
        return 0
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


@router.get("/metrics", response_class=PlainTextResponse)
async def get_metrics(
    db: Session = Depends(get_db),
    x_borg_metrics_token: Optional[str] = Header(default=None),
    authorization: Optional[str] = Header(default=None),
):
    """
    Prometheus metrics endpoint

    Returns metrics in Prometheus text format for scraping.
    """
    metrics_enabled, metrics_require_auth, metrics_token = _resolve_metrics_settings(db)
    if not metrics_enabled:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND, detail="Metrics disabled"
        )

    if metrics_require_auth:
        presented_token = _extract_metrics_token(x_borg_metrics_token, authorization)
        if not metrics_token or presented_token != metrics_token:
            raise HTTPException(
                status_code=http_status.HTTP_401_UNAUTHORIZED,
                detail="Invalid metrics token",
            )

    lines = []

    # Header
    lines.append("# Prometheus metrics for borg-ui")
    lines.append(f"# Generated at {serialize_datetime(datetime.now(timezone.utc))}")
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
            # a repository nobody has measured yet gets no sample: 0 is the
            # size of an emptied repository, and an alert on "dropped to
            # zero" must not fire on an import that was never measured
            size_bytes = stored_size_bytes(repo)
            if size_bytes is None:
                continue
            lines.append(
                f'borg_repository_size_bytes{{repository="{repo.name}"}} {size_bytes}'
            )
        lines.append("")

        lines.append(
            "# HELP borg_repository_archive_count Number of archives in repository"
        )
        lines.append("# TYPE borg_repository_archive_count gauge")
        for repo in repositories:
            lines.append(
                f'borg_repository_archive_count{{repository="{repo.name}"}} {repo.archive_count or 0}'
            )
        lines.append("")

        lines.append(
            "# HELP borg_repository_last_backup_timestamp Unix timestamp of last backup"
        )
        lines.append("# TYPE borg_repository_last_backup_timestamp gauge")
        for repo in repositories:
            timestamp = timestamp_to_unix(repo.last_backup)
            lines.append(
                f'borg_repository_last_backup_timestamp{{repository="{repo.name}"}} {timestamp}'
            )
        lines.append("")

        lines.append(
            "# HELP borg_repository_last_check_timestamp Unix timestamp of last check"
        )
        lines.append("# TYPE borg_repository_last_check_timestamp gauge")
        for repo in repositories:
            timestamp = timestamp_to_unix(repo.last_check)
            lines.append(
                f'borg_repository_last_check_timestamp{{repository="{repo.name}"}} {timestamp}'
            )
        lines.append("")

        lines.append(
            "# HELP borg_repository_last_compact_timestamp Unix timestamp of last compact"
        )
        lines.append("# TYPE borg_repository_last_compact_timestamp gauge")
        for repo in repositories:
            timestamp = timestamp_to_unix(repo.last_compact)
            lines.append(
                f'borg_repository_last_compact_timestamp{{repository="{repo.name}"}} {timestamp}'
            )
        lines.append("")

        # ===== Backup Job Metrics =====
        lines.append(
            "# HELP borg_backup_jobs_total Total number of backup jobs by status"
        )
        lines.append("# TYPE borg_backup_jobs_total gauge")

        for repo_name, status, count in _counts_by_repository(db, "backup"):
            lines.append(
                f'borg_backup_jobs_total{{repository="{repo_name}",status="{status}"}} {count}'
            )
        lines.append("")

        # Always empty since the job tables collapsed into `operations`: an
        # operation cascades with its repository, so a job for a deleted
        # repository cannot exist. The family is kept so existing dashboards
        # keep parsing.
        lines.append(
            "# HELP borg_backup_orphaned_jobs_total Backup jobs for deleted/renamed repositories"
        )
        lines.append("# TYPE borg_backup_orphaned_jobs_total gauge")
        lines.append("")

        lines.append(
            "# HELP borg_backup_last_job_success Last backup job success (1=success, 0=failure)"
        )
        lines.append("# TYPE borg_backup_last_job_success gauge")

        for repo in repositories:
            last_job = latest_backup_job_for_repository(db, repo)

            if last_job:
                success = (
                    1
                    if last_job.status in ("completed", "completed_with_warnings")
                    else 0
                )
                lines.append(
                    f'borg_backup_last_job_success{{repository="{repo.name}"}} {success}'
                )
        lines.append("")

        lines.append(
            "# HELP borg_backup_last_duration_seconds Duration of last backup job in seconds"
        )
        lines.append("# TYPE borg_backup_last_duration_seconds gauge")

        for repo in repositories:
            last_job = latest_backup_job_for_repository(
                db, repo, order="completed", require_timestamps=True
            )

            if last_job and last_job.started_at and last_job.completed_at:
                duration = (last_job.completed_at - last_job.started_at).total_seconds()
                lines.append(
                    f'borg_backup_last_duration_seconds{{repository="{repo.name}"}} {duration:.2f}'
                )
        lines.append("")

        lines.append(
            "# HELP borg_backup_last_original_size_bytes Original size of last backup in bytes"
        )
        lines.append("# TYPE borg_backup_last_original_size_bytes gauge")

        for repo in repositories:
            last_job = latest_backup_job_for_repository(
                db,
                repo,
                statuses=("completed", "completed_with_warnings"),
                order="completed",
            )

            if last_job:
                lines.append(
                    f'borg_backup_last_original_size_bytes{{repository="{repo.name}"}} {last_job.original_size or 0}'
                )
        lines.append("")

        lines.append(
            "# HELP borg_backup_last_deduplicated_size_bytes Deduplicated size of last backup in bytes"
        )
        lines.append("# TYPE borg_backup_last_deduplicated_size_bytes gauge")

        for repo in repositories:
            last_job = latest_backup_job_for_repository(
                db,
                repo,
                statuses=("completed", "completed_with_warnings"),
                order="completed",
            )

            if last_job:
                lines.append(
                    f'borg_backup_last_deduplicated_size_bytes{{repository="{repo.name}"}} {last_job.deduplicated_size or 0}'
                )
        lines.append("")

        # ===== Restore Job Metrics =====
        lines.append(
            "# HELP borg_restore_jobs_total Total number of restore jobs by status"
        )
        lines.append("# TYPE borg_restore_jobs_total gauge")

        for status, count in _counts_by_status(db, "restore"):
            lines.append(f'borg_restore_jobs_total{{status="{status}"}} {count}')
        lines.append("")

        # ===== Check Job Metrics =====
        lines.append(
            "# HELP borg_check_jobs_total Total number of check jobs by status"
        )
        lines.append("# TYPE borg_check_jobs_total gauge")

        for repo_name, status, count in _counts_by_repository(db, "check"):
            lines.append(
                f'borg_check_jobs_total{{repository="{repo_name}",status="{status}"}} {count}'
            )
        lines.append("")

        lines.append(
            "# HELP borg_check_last_duration_seconds Duration of last check job in seconds"
        )
        lines.append("# TYPE borg_check_last_duration_seconds gauge")

        for repo in repositories:
            last_job = _last_finished(db, "check", repo.id)

            if last_job and last_job.started_at and last_job.completed_at:
                duration = (last_job.completed_at - last_job.started_at).total_seconds()
                lines.append(
                    f'borg_check_last_duration_seconds{{repository="{repo.name}"}} {duration:.2f}'
                )
        lines.append("")

        # ===== Compact Job Metrics =====
        lines.append(
            "# HELP borg_compact_jobs_total Total number of compact jobs by status"
        )
        lines.append("# TYPE borg_compact_jobs_total gauge")

        for repo_name, status, count in _counts_by_repository(db, "compact"):
            lines.append(
                f'borg_compact_jobs_total{{repository="{repo_name}",status="{status}"}} {count}'
            )
        lines.append("")

        lines.append(
            "# HELP borg_compact_last_duration_seconds Duration of last compact job in seconds"
        )
        lines.append("# TYPE borg_compact_last_duration_seconds gauge")

        for repo in repositories:
            last_job = _last_finished(db, "compact", repo.id)

            if last_job and last_job.started_at and last_job.completed_at:
                duration = (last_job.completed_at - last_job.started_at).total_seconds()
                lines.append(
                    f'borg_compact_last_duration_seconds{{repository="{repo.name}"}} {duration:.2f}'
                )
        lines.append("")

        # ===== Prune Job Metrics =====
        lines.append(
            "# HELP borg_prune_jobs_total Total number of prune jobs by status"
        )
        lines.append("# TYPE borg_prune_jobs_total gauge")

        for repo_name, status, count in _counts_by_repository(db, "prune"):
            lines.append(
                f'borg_prune_jobs_total{{repository="{repo_name}",status="{status}"}} {count}'
            )
        lines.append("")

        # ===== System Metrics =====
        lines.append("# HELP borg_ui_repositories_total Total number of repositories")
        lines.append("# TYPE borg_ui_repositories_total gauge")
        repo_count = db.query(func.count(Repository.id)).scalar()
        lines.append(f"borg_ui_repositories_total {repo_count}")
        lines.append("")

        lines.append(
            "# HELP borg_ui_scheduled_jobs_total Total number of scheduled jobs"
        )
        lines.append("# TYPE borg_ui_scheduled_jobs_total gauge")
        scheduled_count = db.query(func.count(ScheduledJob.id)).scalar()
        lines.append(f"borg_ui_scheduled_jobs_total {scheduled_count}")
        lines.append("")

        lines.append(
            "# HELP borg_ui_scheduled_jobs_enabled Number of enabled scheduled jobs"
        )
        lines.append("# TYPE borg_ui_scheduled_jobs_enabled gauge")
        enabled_count = (
            db.query(func.count(ScheduledJob.id))
            .filter(ScheduledJob.enabled == True)
            .scalar()
        )
        lines.append(f"borg_ui_scheduled_jobs_enabled {enabled_count}")
        lines.append("")

        lines.append(
            "# HELP borg_ui_active_jobs Number of currently running jobs by type"
        )
        lines.append("# TYPE borg_ui_active_jobs gauge")

        active_backups = _active_count(db, "backup")
        lines.append(f'borg_ui_active_jobs{{type="backup"}} {active_backups}')

        active_restores = _active_count(db, "restore")
        lines.append(f'borg_ui_active_jobs{{type="restore"}} {active_restores}')

        active_checks = _active_count(db, "check")
        lines.append(f'borg_ui_active_jobs{{type="check"}} {active_checks}')

        active_compacts = _active_count(db, "compact")
        lines.append(f'borg_ui_active_jobs{{type="compact"}} {active_compacts}')

        active_prunes = _active_count(db, "prune")
        lines.append(f'borg_ui_active_jobs{{type="prune"}} {active_prunes}')

        lines.append("")

        logger.info(
            "Metrics endpoint accessed",
            metrics_count=len([l for l in lines if not l.startswith("#") and l]),
        )

    except Exception as e:
        logger.error("Failed to generate metrics", error=str(e))
        lines.append(f"# ERROR: {str(e)}")

    return "\n".join(lines)
