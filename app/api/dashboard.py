from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session
from pydantic import BaseModel
import psutil
import structlog
from dataclasses import dataclass, fields
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

from app.database.database import get_db
from app.database.models import (
    User,
    BackupJob,
    Repository,
    ScheduledJob,
    ScheduledJobRepository,
    CheckJob,
    CompactJob,
    RestoreCheckJob,
    SSHConnection,
    SystemSettings,
)
from app.core.security import get_current_user
from app.utils.datetime_utils import serialize_datetime
from app.utils.schedule_time import (
    DEFAULT_SCHEDULE_TIMEZONE,
    calculate_next_cron_run,
    to_utc_naive,
)

logger = structlog.get_logger()
router = APIRouter()

RESTORE_CHECK_WARNING_DAYS = 14
RESTORE_CHECK_CRITICAL_DAYS = 30


@dataclass(frozen=True)
class DashboardHealthThresholds:
    backup_warning_days: int = 3
    backup_critical_days: int = 7
    check_warning_days: int = 7
    check_critical_days: int = 30
    compact_warning_days: int = 30
    compact_critical_days: int = 60
    restore_check_warning_days: int = RESTORE_CHECK_WARNING_DAYS
    restore_check_critical_days: int = RESTORE_CHECK_CRITICAL_DAYS
    observe_freshness_warning_days: int = 2
    observe_freshness_critical_days: int = 7

    @classmethod
    def from_settings(
        cls, settings: Optional[SystemSettings]
    ) -> "DashboardHealthThresholds":
        if not settings:
            return cls()

        values = {}
        for field in fields(cls):
            settings_name = f"dashboard_{field.name}"
            value = getattr(settings, settings_name, None)
            values[field.name] = field.default if value is None else value

        return cls(**values)


# Helper function to format datetime with timezone
def format_datetime(dt):
    """Format datetime to ISO8601 with UTC timezone indicator"""
    return serialize_datetime(dt)


def resolve_schedule_next_run(
    schedule: ScheduledJob, now: datetime
) -> Optional[datetime]:
    """Resolve the next due time for a schedule, preferring stored future values."""
    now_utc = to_utc_naive(now)
    if schedule.next_run and to_utc_naive(schedule.next_run) > now_utc:
        return to_utc_naive(schedule.next_run)

    try:
        return calculate_next_cron_run(
            schedule.cron_expression,
            now_utc,
            schedule.timezone or DEFAULT_SCHEDULE_TIMEZONE,
        )
    except Exception:
        return None


# Pydantic models for responses
class SystemMetrics(BaseModel):
    cpu_usage: float
    cpu_count: int
    memory_usage: float
    memory_total: int
    memory_available: int
    disk_usage: float
    disk_total: int
    disk_free: int
    uptime: int


class ScheduledJobInfo(BaseModel):
    id: int
    name: str
    cron_expression: str
    timezone: str = DEFAULT_SCHEDULE_TIMEZONE
    repository: str = None
    enabled: bool
    last_run: str = None
    next_run: str = None


class DashboardStatus(BaseModel):
    system_metrics: SystemMetrics
    scheduled_jobs: List[ScheduledJobInfo]
    recent_jobs: List[Dict[str, Any]]
    alerts: List[Dict[str, Any]]
    last_updated: str


class MetricsResponse(BaseModel):
    cpu_usage: float
    memory_usage: float
    disk_usage: float
    network_io: Dict[str, float]
    load_average: List[float]


class ScheduleResponse(BaseModel):
    jobs: List[ScheduledJobInfo]
    next_execution: str = None


def promote_repository_health(
    health_status: str, health_color: str, severity: str
) -> tuple[str, str]:
    if severity == "critical":
        return "critical", "error"
    if severity == "warning" and health_status != "critical":
        return "warning", "warning"
    return health_status, health_color


def classify_day_age(days: int, warning_days: int, critical_days: int) -> str:
    if days > critical_days:
        return "critical"
    if days > warning_days:
        return "warning"
    return "healthy"


def build_restore_check_health(
    repo: Repository,
    now: datetime,
    latest_restore_check: Optional[RestoreCheckJob] = None,
    thresholds: Optional[DashboardHealthThresholds] = None,
) -> Dict[str, Any]:
    """Build restore-verification health without penalizing unconfigured repos."""
    thresholds = thresholds or DashboardHealthThresholds()
    configured = bool(repo.restore_check_cron_expression)
    latest_status = latest_restore_check.status if latest_restore_check else None
    latest_error = latest_restore_check.error_message if latest_restore_check else None
    last_success = repo.last_restore_check

    if latest_status == "failed":
        return {
            "dimension": "critical",
            "severity": "critical",
            "warning": f"Restore check failed: {latest_error or 'unknown error'}",
            "configured": configured,
            "latest_status": latest_status,
            "latest_error": latest_error,
        }

    if latest_status == "completed_with_warnings":
        return {
            "dimension": "warning",
            "severity": "warning",
            "warning": "Restore check completed with warnings",
            "configured": configured,
            "latest_status": latest_status,
            "latest_error": latest_error,
        }

    if latest_status == "needs_backup":
        return {
            "dimension": "warning",
            "severity": "warning",
            "warning": latest_error or "Restore check needs a backup first",
            "configured": configured,
            "latest_status": latest_status,
            "latest_error": latest_error,
        }

    if latest_status == "cancelled":
        return {
            "dimension": "warning",
            "severity": "warning",
            "warning": "Latest restore check was cancelled",
            "configured": configured,
            "latest_status": latest_status,
            "latest_error": latest_error,
        }

    if latest_status in ("pending", "running") and not last_success:
        return {
            "dimension": "warning",
            "severity": "warning",
            "warning": "Restore check has not completed yet",
            "configured": configured,
            "latest_status": latest_status,
            "latest_error": latest_error,
        }

    if latest_status == "completed" and not last_success and latest_restore_check:
        last_success = latest_restore_check.completed_at

    if last_success:
        days_since_restore_check = (now - last_success).days
        restore_dim = classify_day_age(
            days_since_restore_check,
            thresholds.restore_check_warning_days,
            thresholds.restore_check_critical_days,
        )
        if restore_dim == "critical":
            return {
                "dimension": "critical",
                "severity": "critical",
                "warning": f"No restore check in {days_since_restore_check} days",
                "configured": configured,
                "latest_status": latest_status,
                "latest_error": latest_error,
            }
        if restore_dim == "warning":
            return {
                "dimension": "warning",
                "severity": "warning",
                "warning": f"Last restore check {days_since_restore_check} days ago",
                "configured": configured,
                "latest_status": latest_status,
                "latest_error": latest_error,
            }
        return {
            "dimension": "healthy",
            "severity": None,
            "warning": None,
            "configured": configured,
            "latest_status": latest_status,
            "latest_error": latest_error,
        }

    if configured:
        return {
            "dimension": "warning",
            "severity": "warning",
            "warning": "Restore check configured but never completed",
            "configured": configured,
            "latest_status": latest_status,
            "latest_error": latest_error,
        }

    return {
        "dimension": "unknown",
        "severity": None,
        "warning": None,
        "configured": configured,
        "latest_status": latest_status,
        "latest_error": latest_error,
    }


def build_full_repository_health(
    repo: Repository,
    now: datetime,
    latest_restore_check: Optional[RestoreCheckJob] = None,
    thresholds: Optional[DashboardHealthThresholds] = None,
) -> Dict[str, Any]:
    """Build health signals for repositories managed directly by Borg UI."""
    thresholds = thresholds or DashboardHealthThresholds()
    health_status = "healthy"
    health_color = "success"
    warnings = []

    if repo.last_backup:
        days_since_backup = (now - repo.last_backup).days
        backup_dim = classify_day_age(
            days_since_backup,
            thresholds.backup_warning_days,
            thresholds.backup_critical_days,
        )
        if backup_dim == "critical":
            health_status = "critical"
            health_color = "error"
            warnings.append(f"No backup in {days_since_backup} days")
        elif backup_dim == "warning":
            health_status = "warning"
            health_color = "warning"
            warnings.append(f"Last backup {days_since_backup} days ago")
    else:
        health_status = "critical"
        health_color = "error"
        warnings.append("Never backed up")
        backup_dim = "critical"

    if repo.last_check:
        days_since_check = (now - repo.last_check).days
        check_dim = classify_day_age(
            days_since_check,
            thresholds.check_warning_days,
            thresholds.check_critical_days,
        )
    else:
        check_dim = "critical"

    if repo.last_compact:
        days_since_compact = (now - repo.last_compact).days
        compact_dim = classify_day_age(
            days_since_compact,
            thresholds.compact_warning_days,
            thresholds.compact_critical_days,
        )
    else:
        compact_dim = "critical"

    restore_check_health = build_restore_check_health(
        repo, now, latest_restore_check, thresholds
    )
    if restore_check_health["severity"]:
        health_status, health_color = promote_repository_health(
            health_status, health_color, restore_check_health["severity"]
        )
    if restore_check_health["warning"]:
        warnings.append(restore_check_health["warning"])

    return {
        "health_status": health_status,
        "health_color": health_color,
        "warnings": warnings,
        "restore_check_configured": restore_check_health["configured"],
        "latest_restore_check_status": restore_check_health["latest_status"],
        "latest_restore_check_error": restore_check_health["latest_error"],
        "dimension_health": {
            "backup": backup_dim,
            "check": check_dim,
            "compact": compact_dim,
            "restore": restore_check_health["dimension"],
        },
    }


def build_observe_repository_health(
    repo: Repository,
    now: datetime,
    latest_restore_check: Optional[RestoreCheckJob] = None,
    thresholds: Optional[DashboardHealthThresholds] = None,
) -> Dict[str, Any]:
    """Build monitoring-oriented health signals for observe-only repositories."""
    thresholds = thresholds or DashboardHealthThresholds()
    freshness_dim = "healthy"
    check_dim = "unknown"
    archives_dim = "healthy"
    health_status = "healthy"
    health_color = "success"
    warnings = []

    if repo.archive_count and repo.archive_count > 0:
        archives_dim = "healthy"
    else:
        archives_dim = "critical"
        health_status = "critical"
        health_color = "error"
        warnings.append("No archives detected")

    if repo.last_backup:
        days_since_archive = (now - repo.last_backup).days
        freshness_dim = classify_day_age(
            days_since_archive,
            thresholds.observe_freshness_warning_days,
            thresholds.observe_freshness_critical_days,
        )
        if freshness_dim == "critical":
            freshness_dim = "critical"
            health_status = "critical"
            health_color = "error"
            warnings.append(f"No new archives in {days_since_archive} days")
        elif freshness_dim == "warning":
            if health_status != "critical":
                health_status = "warning"
                health_color = "warning"
            warnings.append(f"Latest archive {days_since_archive} days old")
    else:
        freshness_dim = "critical"
        health_status = "critical"
        health_color = "error"
        warnings.append("No archive freshness data available")

    if repo.last_check:
        days_since_check = (now - repo.last_check).days
        check_dim = classify_day_age(
            days_since_check,
            thresholds.check_warning_days,
            thresholds.check_critical_days,
        )
        if check_dim in ("critical", "warning") and health_status != "critical":
            health_status = "warning"
            health_color = "warning"

    restore_check_health = build_restore_check_health(
        repo, now, latest_restore_check, thresholds
    )
    if restore_check_health["severity"]:
        health_status, health_color = promote_repository_health(
            health_status, health_color, restore_check_health["severity"]
        )
    if restore_check_health["warning"]:
        warnings.append(restore_check_health["warning"])

    return {
        "health_status": health_status,
        "health_color": health_color,
        "warnings": warnings,
        "restore_check_configured": restore_check_health["configured"],
        "latest_restore_check_status": restore_check_health["latest_status"],
        "latest_restore_check_error": restore_check_health["latest_error"],
        "dimension_health": {
            # Reused as Freshness / Check / Archives on the frontend for observe-only repos.
            "backup": freshness_dim,
            "check": check_dim,
            "compact": archives_dim,
            "restore": restore_check_health["dimension"],
        },
    }


def get_system_metrics() -> SystemMetrics:
    """Get system resource metrics"""
    try:
        try:
            cpu_usage = psutil.cpu_percent(interval=1)
            cpu_count = psutil.cpu_count(logical=True) or 1
        except Exception as e:
            logger.warning("Failed to read CPU metrics", error=str(e))
            cpu_usage = 0.0
            cpu_count = 1

        try:
            memory = psutil.virtual_memory()
            memory_usage = memory.percent
            memory_total = memory.total
            memory_available = memory.available
        except Exception as e:
            logger.warning("Failed to read memory metrics", error=str(e))
            memory_usage = 0.0
            memory_total = 0
            memory_available = 0

        try:
            disk = psutil.disk_usage("/")
            disk_usage = disk.percent
            disk_total = disk.total
            disk_free = disk.free
        except Exception as e:
            logger.warning("Failed to read disk metrics", error=str(e))
            disk_usage = 0.0
            disk_total = 0
            disk_free = 0

        try:
            uptime = int(psutil.boot_time())
        except Exception as e:
            logger.warning("Failed to read system uptime", error=str(e))
            uptime = 0

        return SystemMetrics(
            cpu_usage=cpu_usage,
            cpu_count=cpu_count,
            memory_usage=memory_usage,
            memory_total=memory_total,
            memory_available=memory_available,
            disk_usage=disk_usage,
            disk_total=disk_total,
            disk_free=disk_free,
            uptime=uptime,
        )
    except Exception as e:
        logger.error("Failed to get system metrics", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"key": "backend.errors.dashboard.failedGetSystemMetrics"},
        )


def get_scheduled_jobs(db: Session) -> List[ScheduledJobInfo]:
    """Get scheduled jobs information"""
    # TODO: Implement when ScheduledJob model is added back
    return []


def get_recent_jobs(db: Session, limit: int = 10) -> List[Dict[str, Any]]:
    """Get recent backup jobs"""
    try:
        jobs = (
            db.query(BackupJob).order_by(BackupJob.started_at.desc()).limit(limit).all()
        )
        job_list = []

        for job in jobs:
            # Determine trigger type
            triggered_by = "schedule" if job.scheduled_job_id else "manual"

            job_list.append(
                {
                    "id": job.id,
                    "repository": job.repository,
                    "status": job.status,
                    "started_at": format_datetime(job.started_at),
                    "completed_at": format_datetime(job.completed_at),
                    "progress": job.progress,
                    "error_message": job.error_message,
                    "triggered_by": triggered_by,
                    "schedule_id": job.scheduled_job_id,
                    "has_logs": bool(job.log_file_path or job.logs),
                }
            )

        return job_list
    except Exception as e:
        logger.error("Failed to get recent jobs", error=str(e))
        return []


def get_alerts(db: Session, hours: int = 24) -> List[Dict[str, Any]]:
    """Get recent system alerts"""
    # TODO: Implement when SystemLog model is added back
    return []


@router.get("/status", response_model=DashboardStatus)
async def get_dashboard_status(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Get comprehensive dashboard status"""
    try:
        # Get system metrics
        system_metrics = get_system_metrics()

        # Get scheduled jobs
        scheduled_jobs = get_scheduled_jobs(db)

        # Get recent jobs
        recent_jobs = get_recent_jobs(db)

        # Get alerts
        alerts = get_alerts(db)

        return DashboardStatus(
            system_metrics=system_metrics,
            scheduled_jobs=scheduled_jobs,
            recent_jobs=recent_jobs,
            alerts=alerts,
            last_updated=format_datetime(datetime.utcnow()),
        )
    except Exception as e:
        logger.error("Error getting dashboard status", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"key": "backend.errors.dashboard.failedGetDashboardStatus"},
        )


@router.get("/metrics", response_model=MetricsResponse)
async def get_dashboard_metrics(current_user: User = Depends(get_current_user)):
    """Get system metrics for dashboard"""
    try:
        # CPU usage
        cpu_usage = psutil.cpu_percent(interval=1)

        # Memory usage
        memory = psutil.virtual_memory()

        # Disk usage
        disk = psutil.disk_usage("/")

        # Network I/O
        network = psutil.net_io_counters()

        # Load average
        load_avg = psutil.getloadavg()

        return MetricsResponse(
            cpu_usage=cpu_usage,
            memory_usage=memory.percent,
            disk_usage=disk.percent,
            network_io={
                "bytes_sent": network.bytes_sent,
                "bytes_recv": network.bytes_recv,
                "packets_sent": network.packets_sent,
                "packets_recv": network.packets_recv,
            },
            load_average=list(load_avg),
        )
    except Exception as e:
        logger.error("Error getting metrics", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"key": "backend.errors.dashboard.failedGetMetrics"},
        )


@router.get("/schedule", response_model=ScheduleResponse)
async def get_dashboard_schedule(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Get scheduled jobs information"""
    try:
        jobs = get_scheduled_jobs(db)

        # Find next execution time
        next_execution = None
        if jobs:
            # This is a simplified approach - in a real implementation,
            # you'd use a proper cron parser to calculate next execution
            next_execution = format_datetime(datetime.utcnow())

        return ScheduleResponse(jobs=jobs, next_execution=next_execution)
    except Exception as e:
        logger.error("Error getting schedule", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"key": "backend.errors.dashboard.failedGetSchedule"},
        )


@router.get("/overview")
async def get_dashboard_overview(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Get comprehensive dashboard overview with repository health, trends, and maintenance alerts"""
    try:
        now = datetime.utcnow()
        settings = db.query(SystemSettings).first()
        health_thresholds = DashboardHealthThresholds.from_settings(settings)

        # Get all repositories
        repositories = db.query(Repository).all()

        # Separate full-mode repos (for health/maintenance) from observe-only repos
        full_mode_repos = [r for r in repositories if r.mode != "observe"]
        observe_only_repos = [r for r in repositories if r.mode == "observe"]

        # Get all schedules
        schedules = db.query(ScheduledJob).all()

        # Get SSH connections
        ssh_connections = db.query(SSHConnection).all()

        latest_restore_checks = {}
        repository_ids = [repo.id for repo in repositories]
        if repository_ids:
            latest_restore_check_ids = (
                db.query(func.max(RestoreCheckJob.id).label("id"))
                .filter(RestoreCheckJob.repository_id.in_(repository_ids))
                .group_by(RestoreCheckJob.repository_id)
                .subquery()
            )
            restore_check_jobs = (
                db.query(RestoreCheckJob)
                .join(
                    latest_restore_check_ids,
                    RestoreCheckJob.id == latest_restore_check_ids.c.id,
                )
                .all()
            )
            for restore_check_job in restore_check_jobs:
                latest_restore_checks[restore_check_job.repository_id] = (
                    restore_check_job
                )

        # Calculate repository health (only for full-mode repos that do backups)
        repo_health = []
        total_size_bytes = 0
        total_archives = 0

        # Include all repos for size/archive totals
        for repo in repositories:
            size_bytes = parse_size_to_bytes(repo.total_size)
            total_size_bytes += size_bytes
            total_archives += repo.archive_count or 0

        # Show health for both repo modes, but with mode-specific semantics.
        for repo in full_mode_repos:
            # Parse size for this repo
            size_bytes = parse_size_to_bytes(repo.total_size)
            latest_restore_check = latest_restore_checks.get(repo.id)
            health = build_full_repository_health(
                repo, now, latest_restore_check, health_thresholds
            )

            # Get associated schedule — prefer enabled over disabled when multiple match
            repo_schedule = None
            fallback_schedule = None
            for schedule in schedules:
                matched = False
                if schedule.repository_id == repo.id:
                    matched = True
                else:
                    multi_repos = (
                        db.query(ScheduledJobRepository)
                        .filter(
                            ScheduledJobRepository.scheduled_job_id == schedule.id,
                            ScheduledJobRepository.repository_id == repo.id,
                        )
                        .first()
                    )
                    if multi_repos:
                        matched = True
                if matched:
                    if schedule.enabled:
                        repo_schedule = schedule
                        break  # enabled match wins immediately
                    elif fallback_schedule is None:
                        fallback_schedule = schedule  # keep first disabled as fallback
            if repo_schedule is None:
                repo_schedule = fallback_schedule

            # Calculate dedup ratio (if we have the data)
            dedup_ratio = None
            if (
                hasattr(repo, "deduplicated_size")
                and repo.deduplicated_size
                and size_bytes > 0
            ):
                dedup_bytes = parse_size_to_bytes(repo.deduplicated_size)
                dedup_ratio = (
                    int((1 - (dedup_bytes / size_bytes)) * 100) if size_bytes > 0 else 0
                )

            repo_health.append(
                {
                    "id": repo.id,
                    "name": repo.name,
                    "path": repo.path,
                    "type": repo.repository_type or "local",
                    "mode": repo.mode or "full",
                    "last_backup": serialize_datetime(repo.last_backup),
                    "last_check": serialize_datetime(repo.last_check),
                    "last_compact": serialize_datetime(repo.last_compact),
                    "last_restore_check": serialize_datetime(repo.last_restore_check),
                    "archive_count": repo.archive_count or 0,
                    "total_size": repo.total_size,
                    "size_bytes": size_bytes,
                    "health_status": health["health_status"],
                    "health_color": health["health_color"],
                    "warnings": health["warnings"],
                    "restore_check_configured": health["restore_check_configured"],
                    "latest_restore_check_status": health[
                        "latest_restore_check_status"
                    ],
                    "latest_restore_check_error": health["latest_restore_check_error"],
                    "dedup_ratio": dedup_ratio,
                    "has_schedule": repo_schedule is not None,
                    "schedule_enabled": repo_schedule.enabled
                    if repo_schedule
                    else False,
                    "schedule_name": repo_schedule.name if repo_schedule else None,
                    "next_run": serialize_datetime(repo_schedule.next_run)
                    if (
                        repo_schedule
                        and repo_schedule.enabled
                        and repo_schedule.next_run
                    )
                    else None,
                    "dimension_health": health["dimension_health"],
                }
            )

        for repo in observe_only_repos:
            size_bytes = parse_size_to_bytes(repo.total_size)
            latest_restore_check = latest_restore_checks.get(repo.id)
            health = build_observe_repository_health(
                repo, now, latest_restore_check, health_thresholds
            )

            repo_health.append(
                {
                    "id": repo.id,
                    "name": repo.name,
                    "path": repo.path,
                    "type": repo.repository_type or "local",
                    "mode": repo.mode or "observe",
                    "last_backup": serialize_datetime(repo.last_backup),
                    "last_check": serialize_datetime(repo.last_check),
                    "last_compact": serialize_datetime(repo.last_compact),
                    "last_restore_check": serialize_datetime(repo.last_restore_check),
                    "archive_count": repo.archive_count or 0,
                    "total_size": repo.total_size,
                    "size_bytes": size_bytes,
                    "health_status": health["health_status"],
                    "health_color": health["health_color"],
                    "warnings": health["warnings"],
                    "restore_check_configured": health["restore_check_configured"],
                    "latest_restore_check_status": health[
                        "latest_restore_check_status"
                    ],
                    "latest_restore_check_error": health["latest_restore_check_error"],
                    "dedup_ratio": None,
                    "has_schedule": False,
                    "schedule_enabled": False,
                    "schedule_name": None,
                    "next_run": None,
                    "dimension_health": health["dimension_health"],
                }
            )

        # Calculate backup success rate (last 30 days)
        thirty_days_ago = now - timedelta(days=30)
        recent_jobs = (
            db.query(BackupJob).filter(BackupJob.started_at >= thirty_days_ago).all()
        )

        # Only count terminal jobs — running/pending skew the rate and don't match passed+failed
        terminal_jobs = [j for j in recent_jobs if j.status in ("completed", "failed")]
        total_jobs = len(terminal_jobs)
        successful_jobs = len([j for j in terminal_jobs if j.status == "completed"])
        failed_jobs = len([j for j in terminal_jobs if j.status == "failed"])
        success_rate = (successful_jobs / total_jobs * 100) if total_jobs > 0 else 0

        # Group jobs by week for trend
        backup_trends = []
        for week in range(4):
            week_start = now - timedelta(days=(4 - week) * 7)
            week_end = week_start + timedelta(days=7)
            week_jobs = [
                j for j in recent_jobs if week_start <= j.started_at < week_end
            ]
            week_success = len([j for j in week_jobs if j.status == "completed"])
            week_total = len(week_jobs)
            week_rate = (week_success / week_total * 100) if week_total > 0 else 0

            backup_trends.append(
                {
                    "week": f"Week {week + 1}",
                    "success_rate": round(week_rate, 1),
                    "successful": week_success,
                    "failed": len([j for j in week_jobs if j.status == "failed"]),
                    "total": week_total,
                }
            )

        # Get upcoming schedules (next 24 hours)
        end_time = now + timedelta(hours=24)
        active_schedules = [s for s in schedules if s.enabled]
        upcoming_tasks = []
        for schedule in active_schedules:
            next_run_dt = resolve_schedule_next_run(schedule, now)
            if not next_run_dt or next_run_dt > end_time:
                continue

            # Get repository info for this schedule
            repo_names = []
            if schedule.repository_id:
                # Single-repo schedule
                repo = (
                    db.query(Repository)
                    .filter(Repository.id == schedule.repository_id)
                    .first()
                )
                if repo:
                    repo_names.append(repo.name)
            else:
                # Multi-repo schedule - get all associated repos
                multi_repos = (
                    db.query(ScheduledJobRepository)
                    .filter(ScheduledJobRepository.scheduled_job_id == schedule.id)
                    .all()
                )
                for mr in multi_repos:
                    repo = (
                        db.query(Repository)
                        .filter(Repository.id == mr.repository_id)
                        .first()
                    )
                    if repo:
                        repo_names.append(repo.name)

            upcoming_tasks.append(
                {
                    "id": schedule.id,
                    "name": schedule.name,
                    "repositories": repo_names,
                    "cron": schedule.cron_expression,
                    "timezone": schedule.timezone or DEFAULT_SCHEDULE_TIMEZONE,
                    "next_run": serialize_datetime(next_run_dt),
                }
            )

        upcoming_tasks.sort(key=lambda item: item["next_run"])
        upcoming_tasks = upcoming_tasks[:10]

        # Get maintenance alerts (only for full-mode repos - observe-only repos don't need maintenance)
        maintenance_alerts = []

        # Check repos needing maintenance
        for repo in full_mode_repos:
            if repo.last_check:
                days_since_check = (now - repo.last_check).days
                if days_since_check > health_thresholds.check_critical_days:
                    maintenance_alerts.append(
                        {
                            "type": "check_overdue",
                            "severity": "warning"
                            if days_since_check
                            < health_thresholds.check_critical_days * 2
                            else "error",
                            "repository": repo.name,
                            "repository_id": repo.id,
                            "message": f"Check overdue by {days_since_check} days",
                            "action": "schedule_check",
                        }
                    )
            else:
                maintenance_alerts.append(
                    {
                        "type": "check_never",
                        "severity": "warning",
                        "repository": repo.name,
                        "repository_id": repo.id,
                        "message": "Never checked",
                        "action": "schedule_check",
                    }
                )

            if repo.last_compact:
                days_since_compact = (now - repo.last_compact).days
                if days_since_compact > health_thresholds.compact_critical_days:
                    maintenance_alerts.append(
                        {
                            "type": "compact_recommended",
                            "severity": "info",
                            "repository": repo.name,
                            "repository_id": repo.id,
                            "message": f"Compact recommended ({days_since_compact}d ago)",
                            "action": "schedule_compact",
                        }
                    )
            else:
                maintenance_alerts.append(
                    {
                        "type": "compact_never",
                        "severity": "info",
                        "repository": repo.name,
                        "repository_id": repo.id,
                        "message": "Never compacted",
                        "action": "schedule_compact",
                    }
                )

        # Get activity for the last 14 days — matches the timeline window exactly
        fourteen_days_ago = now - timedelta(days=14)
        recent_backups = (
            db.query(BackupJob).filter(BackupJob.started_at >= fourteen_days_ago).all()
        )
        recent_checks = (
            db.query(CheckJob).filter(CheckJob.started_at >= fourteen_days_ago).all()
        )
        recent_compacts = (
            db.query(CompactJob)
            .filter(CompactJob.started_at >= fourteen_days_ago)
            .all()
        )
        recent_restore_checks = (
            db.query(RestoreCheckJob)
            .filter(RestoreCheckJob.started_at >= fourteen_days_ago)
            .all()
        )

        # Create a lookup map for repository paths to names (with normalized paths)
        repo_name_map = {}
        repo_id_map = {}
        for repo in repositories:
            # Store by exact path and normalized path (no trailing slash)
            repo_name_map[repo.path] = repo.name
            repo_name_map[repo.path.rstrip("/")] = repo.name
            repo_id_map[repo.id] = repo.name

        activity_feed = []

        for job in recent_backups:
            # Try multiple ways to get repo name
            repo_name = None
            # Try exact match
            if job.repository in repo_name_map:
                repo_name = repo_name_map[job.repository]
            # Try normalized
            elif job.repository and job.repository.rstrip("/") in repo_name_map:
                repo_name = repo_name_map[job.repository.rstrip("/")]
            # Try by repository_id if it exists
            elif (
                hasattr(job, "repository_id")
                and job.repository_id
                and job.repository_id in repo_id_map
            ):
                repo_name = repo_id_map[job.repository_id]
            # Fallback: use last part of path as name
            else:
                repo_name = (
                    job.repository.rstrip("/").split("/")[-1]
                    if job.repository
                    else "Unknown"
                )

            activity_feed.append(
                {
                    "id": job.id,
                    "type": "backup",
                    "status": job.status,
                    "repository": repo_name,
                    "timestamp": serialize_datetime(job.started_at),
                    "message": f"Backup {job.status}",
                    "error": job.error_message if job.status == "failed" else None,
                }
            )

        for job in recent_checks:
            # Try multiple ways to get repo name
            repo_name = None
            if job.repository_path in repo_name_map:
                repo_name = repo_name_map[job.repository_path]
            elif (
                job.repository_path and job.repository_path.rstrip("/") in repo_name_map
            ):
                repo_name = repo_name_map[job.repository_path.rstrip("/")]
            elif (
                hasattr(job, "repository_id")
                and job.repository_id
                and job.repository_id in repo_id_map
            ):
                repo_name = repo_id_map[job.repository_id]
            else:
                repo_name = (
                    job.repository_path.rstrip("/").split("/")[-1]
                    if job.repository_path
                    else "Unknown"
                )

            activity_feed.append(
                {
                    "id": job.id,
                    "type": "check",
                    "status": job.status,
                    "repository": repo_name,
                    "timestamp": serialize_datetime(job.started_at),
                    "message": f"Check {job.status}",
                    "error": job.error_message if job.status == "failed" else None,
                }
            )

        for job in recent_compacts:
            # Try multiple ways to get repo name
            repo_name = None
            if job.repository_path in repo_name_map:
                repo_name = repo_name_map[job.repository_path]
            elif (
                job.repository_path and job.repository_path.rstrip("/") in repo_name_map
            ):
                repo_name = repo_name_map[job.repository_path.rstrip("/")]
            elif (
                hasattr(job, "repository_id")
                and job.repository_id
                and job.repository_id in repo_id_map
            ):
                repo_name = repo_id_map[job.repository_id]
            else:
                repo_name = (
                    job.repository_path.rstrip("/").split("/")[-1]
                    if job.repository_path
                    else "Unknown"
                )

            activity_feed.append(
                {
                    "id": job.id,
                    "type": "compact",
                    "status": job.status,
                    "repository": repo_name,
                    "timestamp": serialize_datetime(job.started_at),
                    "message": f"Compact {job.status}",
                    "error": job.error_message if job.status == "failed" else None,
                }
            )

        for job in recent_restore_checks:
            repo_name = None
            if job.repository_path in repo_name_map:
                repo_name = repo_name_map[job.repository_path]
            elif (
                job.repository_path and job.repository_path.rstrip("/") in repo_name_map
            ):
                repo_name = repo_name_map[job.repository_path.rstrip("/")]
            elif job.repository_id and job.repository_id in repo_id_map:
                repo_name = repo_id_map[job.repository_id]
            else:
                repo_name = (
                    job.repository_path.rstrip("/").split("/")[-1]
                    if job.repository_path
                    else "Unknown"
                )

            activity_feed.append(
                {
                    "id": job.id,
                    "type": "restore_check",
                    "status": job.status,
                    "repository": repo_name,
                    "timestamp": serialize_datetime(job.started_at),
                    "message": f"Restore check {job.status}",
                    "error": job.error_message if job.status == "failed" else None,
                }
            )

        activity_feed.sort(key=lambda x: x["timestamp"] or "", reverse=True)

        # Count SSH connections (active = status is "connected")
        ssh_active = len([c for c in ssh_connections if c.status == "connected"])
        ssh_total = len(ssh_connections)

        # Get system metrics
        system_metrics = get_system_metrics()

        return {
            "summary": {
                "total_repositories": len(repositories),
                "local_repositories": len(
                    [r for r in repositories if r.repository_type == "local"]
                ),
                "ssh_repositories": len(
                    [r for r in repositories if r.repository_type == "ssh"]
                ),
                "active_schedules": len([s for s in schedules if s.enabled]),
                "total_schedules": len(schedules),
                "ssh_connections_active": ssh_active,
                "ssh_connections_total": ssh_total,
                "success_rate_30d": round(success_rate, 1),
                "successful_jobs_30d": successful_jobs,
                "failed_jobs_30d": failed_jobs,
                "total_jobs_30d": total_jobs,
            },
            "storage": {
                "total_size": format_bytes(total_size_bytes),
                "total_size_bytes": total_size_bytes,
                "total_archives": total_archives,
                "average_dedup_ratio": calculate_average_dedup(repositories),
                "breakdown": sorted(
                    [
                        {
                            "name": repo.name,
                            "size": repo.total_size,
                            "size_bytes": parse_size_to_bytes(repo.total_size),
                            "percentage": round(
                                (
                                    parse_size_to_bytes(repo.total_size)
                                    / total_size_bytes
                                    * 100
                                ),
                                1,
                            )
                            if total_size_bytes > 0
                            else 0,
                        }
                        for repo in repositories
                    ],
                    key=lambda x: x["size_bytes"],
                    reverse=True,
                ),
            },
            "repository_health": sorted(
                repo_health,
                key=lambda x: (
                    0
                    if x["health_status"] == "critical"
                    else 1
                    if x["health_status"] == "warning"
                    else 2
                ),
            ),
            "backup_trends": backup_trends,
            "upcoming_tasks": upcoming_tasks,
            "activity_feed": activity_feed,
            "system_metrics": system_metrics.dict(),
            "last_updated": serialize_datetime(now),
        }

    except Exception as e:
        logger.error("Error getting dashboard overview", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get dashboard overview: {str(e)}",
        )


def parse_size_to_bytes(size_str: str) -> int:
    """Parse human-readable size string to bytes"""
    if not size_str:
        return 0

    size_str = size_str.strip().upper()

    # Remove spaces
    size_str = size_str.replace(" ", "")

    # Check units from longest to shortest to avoid matching 'B' in 'GB'
    multipliers = [
        ("PB", 1024**5),
        ("TB", 1024**4),
        ("GB", 1024**3),
        ("MB", 1024**2),
        ("KB", 1024),
        ("B", 1),
    ]

    for unit, multiplier in multipliers:
        if size_str.endswith(unit):
            try:
                number = float(size_str[: -len(unit)])
                return int(number * multiplier)
            except ValueError:
                return 0

    # Try parsing as plain number
    try:
        return int(float(size_str))
    except ValueError:
        return 0


def format_bytes(bytes_value: int) -> str:
    """Format bytes to human-readable string"""
    for unit in ["B", "KB", "MB", "GB", "TB", "PB"]:
        if bytes_value < 1024.0:
            return f"{bytes_value:.1f} {unit}"
        bytes_value /= 1024.0
    return f"{bytes_value:.1f} PB"


def calculate_average_dedup(repositories: List[Repository]) -> int:
    """Calculate average deduplication ratio across repositories"""
    # This is a placeholder - would need actual dedup data from borg info
    # For now, return None to indicate we don't have this data
    return None
