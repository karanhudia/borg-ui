from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from croniter import croniter
from sqlalchemy.orm import Session

from app.database.models import BackupJob, Repository, SystemSettings
from app.services.notification_service import NotificationService
from app.utils.datetime_utils import serialize_datetime
from app.utils.schedule_time import (
    DEFAULT_SCHEDULE_TIMEZONE,
    get_container_timezone,
    normalize_schedule_timezone,
)


DEFAULT_STALE_AFTER_DAYS = 3
DEFAULT_MONITORING_INTERVAL_HOURS = 24
DEFAULT_ALERT_COOLDOWN_HOURS = 24
DEFAULT_REPORT_FREQUENCY = "weekly"
DEFAULT_REPORT_HOUR_UTC = 8
DEFAULT_REPORT_WEEKDAY = 0
DEFAULT_REPORT_MONTHDAY = 1
DEFAULT_REPORT_CRON_EXPRESSION = "0 8 * * 1"
REPORT_FREQUENCIES = {"daily", "weekly", "monthly"}


@dataclass(frozen=True)
class StaleRepository:
    id: int
    name: str
    path: str
    mode: str
    last_backup: Optional[datetime]
    days_since_backup: Optional[int]
    archive_count: int
    reason: str


@dataclass(frozen=True)
class BackupReport:
    title: str
    body: str
    repository_count: int
    stale_count: int
    recent_backup_count: int


def _utc_now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _to_utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _to_utc_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _normalize_now(now: Optional[datetime]) -> datetime:
    if now is None:
        return _utc_now_naive()
    return _to_utc_naive(now)


def _get_or_create_settings(db: Session) -> SystemSettings:
    settings = db.query(SystemSettings).first()
    if settings:
        return settings

    settings = SystemSettings()
    db.add(settings)
    db.flush()
    return settings


def find_stale_repositories(
    db: Session,
    now: datetime,
    *,
    stale_after_days: int,
    include_observe_repos: bool,
) -> list[StaleRepository]:
    """Return repositories with no known backup newer than the configured age."""
    now_naive = _normalize_now(now)
    stale: list[StaleRepository] = []

    repositories = db.query(Repository).order_by(Repository.id.asc()).all()
    for repo in repositories:
        mode = repo.mode or "full"
        if mode == "observe" and not include_observe_repos:
            continue

        if repo.last_backup is None:
            stale.append(
                StaleRepository(
                    id=repo.id,
                    name=repo.name,
                    path=repo.path,
                    mode=mode,
                    last_backup=None,
                    days_since_backup=None,
                    archive_count=repo.archive_count or 0,
                    reason="never_backed_up",
                )
            )
            continue

        last_backup = _to_utc_naive(repo.last_backup)
        days_since_backup = (now_naive - last_backup).days
        if days_since_backup >= stale_after_days:
            stale.append(
                StaleRepository(
                    id=repo.id,
                    name=repo.name,
                    path=repo.path,
                    mode=mode,
                    last_backup=last_backup,
                    days_since_backup=days_since_backup,
                    archive_count=repo.archive_count or 0,
                    reason="stale",
                )
            )

    return stale


def is_monitoring_due(
    settings: SystemSettings, now: datetime, *, force: bool = False
) -> bool:
    if force:
        return True
    if not settings.backup_monitoring_enabled:
        return False

    interval_hours = (
        settings.backup_monitoring_interval_hours or DEFAULT_MONITORING_INTERVAL_HOURS
    )
    last_checked = settings.backup_monitoring_last_checked_at
    if last_checked is None:
        return True

    return _normalize_now(now) - _to_utc_naive(last_checked) >= timedelta(
        hours=interval_hours
    )


def _alert_cooldown_elapsed(settings: SystemSettings, now: datetime) -> bool:
    cooldown_hours = (
        settings.backup_monitoring_alert_cooldown_hours
        if settings.backup_monitoring_alert_cooldown_hours is not None
        else DEFAULT_ALERT_COOLDOWN_HOURS
    )
    if cooldown_hours <= 0:
        return True
    last_alert = settings.backup_monitoring_last_alert_sent_at
    if last_alert is None:
        return True

    return _normalize_now(now) - _to_utc_naive(last_alert) >= timedelta(
        hours=cooldown_hours
    )


async def run_backup_monitoring(
    db: Session, now: Optional[datetime] = None, *, force: bool = False
) -> dict:
    now_naive = _normalize_now(now)
    settings = _get_or_create_settings(db)

    if not is_monitoring_due(settings, now_naive, force=force):
        return {"skipped": True, "reason": "not_due", "stale_count": 0}

    stale_repositories = find_stale_repositories(
        db,
        now_naive,
        stale_after_days=settings.backup_monitoring_stale_after_days
        or DEFAULT_STALE_AFTER_DAYS,
        include_observe_repos=settings.backup_monitoring_include_observe_repos,
    )

    settings.backup_monitoring_last_checked_at = now_naive
    alert_sent = False
    if stale_repositories and _alert_cooldown_elapsed(settings, now_naive):
        await NotificationService.send_stale_backup_alert(
            db,
            stale_repositories,
            settings.backup_monitoring_stale_after_days or DEFAULT_STALE_AFTER_DAYS,
        )
        settings.backup_monitoring_last_alert_sent_at = now_naive
        alert_sent = True

    db.commit()
    return {
        "skipped": False,
        "stale_count": len(stale_repositories),
        "alert_sent": alert_sent,
        "checked_at": serialize_datetime(now_naive),
        "repositories": [
            {
                "id": repo.id,
                "name": repo.name,
                "path": repo.path,
                "mode": repo.mode,
                "last_backup": serialize_datetime(repo.last_backup),
                "days_since_backup": repo.days_since_backup,
                "reason": repo.reason,
            }
            for repo in stale_repositories
        ],
    }


def _legacy_report_cron_expression(settings: SystemSettings) -> str:
    hour = settings.backup_reports_hour_utc
    if hour is None:
        hour = DEFAULT_REPORT_HOUR_UTC

    frequency = settings.backup_reports_frequency or DEFAULT_REPORT_FREQUENCY
    if frequency == "daily":
        return f"0 {hour} * * *"

    if frequency == "monthly":
        monthday = (
            settings.backup_reports_monthday
            if settings.backup_reports_monthday is not None
            else DEFAULT_REPORT_MONTHDAY
        )
        return f"0 {hour} {monthday} * *"

    weekday = (
        settings.backup_reports_weekday
        if settings.backup_reports_weekday is not None
        else DEFAULT_REPORT_WEEKDAY
    )
    cron_weekday = (weekday + 1) % 7
    return f"0 {hour} * * {cron_weekday}"


def _report_cron_expression(settings: SystemSettings) -> str:
    return (
        getattr(settings, "backup_reports_cron_expression", None)
        or _legacy_report_cron_expression(settings)
        or DEFAULT_REPORT_CRON_EXPRESSION
    )


def _report_timezone(settings: SystemSettings) -> str:
    return normalize_schedule_timezone(
        getattr(settings, "backup_reports_timezone", None)
        or get_container_timezone(DEFAULT_SCHEDULE_TIMEZONE)
    )


def _report_window_start(settings: SystemSettings, now: datetime) -> Optional[datetime]:
    try:
        schedule_timezone = _report_timezone(settings)
        schedule_tz = ZoneInfo(schedule_timezone)
        now_local = _to_utc_aware(now).astimezone(schedule_tz)
        cron = croniter(
            _report_cron_expression(settings), now_local + timedelta(seconds=1)
        )
        window_start = cron.get_prev(datetime)
        if window_start.tzinfo is None:
            window_start = window_start.replace(tzinfo=schedule_tz)
        return _to_utc_naive(window_start)
    except Exception:
        return None


def _report_activity_period_start(settings: SystemSettings, now: datetime) -> datetime:
    now_naive = _normalize_now(now)
    frequency = settings.backup_reports_frequency or DEFAULT_REPORT_FREQUENCY

    if frequency == "daily":
        return now_naive - timedelta(days=1)

    if frequency == "monthly":
        year = now_naive.year
        month = now_naive.month - 1
        if month == 0:
            year -= 1
            month = 12
        day = min(now_naive.day, calendar.monthrange(year, month)[1])
        return now_naive.replace(year=year, month=month, day=day)

    return now_naive - timedelta(days=7)


def is_report_due(
    settings: SystemSettings, now: datetime, *, force: bool = False
) -> bool:
    if force:
        return True
    if not settings.backup_reports_enabled:
        return False
    if (settings.backup_reports_frequency or DEFAULT_REPORT_FREQUENCY) not in (
        REPORT_FREQUENCIES
    ):
        return False

    window_start = _report_window_start(settings, now)
    if window_start is None:
        return False

    last_sent = settings.backup_reports_last_sent_at
    if last_sent is None:
        return True
    return _to_utc_naive(last_sent) < window_start


def build_backup_report(
    db: Session, settings: SystemSettings, now: Optional[datetime] = None
) -> BackupReport:
    now_naive = _normalize_now(now)
    repositories = db.query(Repository).order_by(Repository.name.asc()).all()
    stale_repositories = find_stale_repositories(
        db,
        now_naive,
        stale_after_days=settings.backup_monitoring_stale_after_days
        or DEFAULT_STALE_AFTER_DAYS,
        include_observe_repos=settings.backup_monitoring_include_observe_repos,
    )
    period_start = _report_activity_period_start(settings, now_naive)
    recent_jobs = (
        db.query(BackupJob)
        .filter(
            BackupJob.started_at.isnot(None),
            BackupJob.started_at >= period_start,
            BackupJob.started_at <= now_naive,
        )
        .order_by(BackupJob.started_at.desc())
        .limit(10)
        .all()
    )

    lines = [f"Backup report generated {serialize_datetime(now_naive)}", ""]
    if settings.backup_reports_include_summary:
        total_archives = sum(repo.archive_count or 0 for repo in repositories)
        lines.extend(
            [
                "Summary",
                f"- Repositories: {len(repositories)}",
                f"- Total archives: {total_archives}",
                f"- Stale repositories: {len(stale_repositories)}",
                "",
            ]
        )

    if settings.backup_reports_include_stale_repositories:
        lines.append("Stale repositories")
        if stale_repositories:
            for repo in stale_repositories:
                freshness = (
                    "never backed up"
                    if repo.reason == "never_backed_up"
                    else f"{repo.days_since_backup} day(s) old"
                )
                lines.append(f"- {repo.name}: {freshness}")
        else:
            lines.append("- None")
        lines.append("")

    if settings.backup_reports_include_recent_activity:
        lines.append("Recent backup activity")
        lines.append(
            "Activity window: "
            f"{serialize_datetime(period_start)} to {serialize_datetime(now_naive)}"
        )
        if recent_jobs:
            for job in recent_jobs:
                started_at = serialize_datetime(job.started_at)
                lines.append(f"- {job.repository}: {job.status} at {started_at}")
        else:
            lines.append("- No backup jobs started in this activity window")
        lines.append("")

    return BackupReport(
        title="Borg UI backup report",
        body="\n".join(lines).strip(),
        repository_count=len(repositories),
        stale_count=len(stale_repositories),
        recent_backup_count=len(recent_jobs),
    )


async def send_backup_report_now(
    db: Session, now: Optional[datetime] = None, *, force: bool = True
) -> dict:
    now_naive = _normalize_now(now)
    settings = _get_or_create_settings(db)
    if not force and not is_report_due(settings, now_naive):
        return {"sent": False, "reason": "not_due", "repository_count": 0}

    report = build_backup_report(db, settings, now_naive)
    await NotificationService.send_backup_report(db, report.title, report.body)
    settings.backup_reports_last_sent_at = now_naive
    db.commit()
    return {
        "sent": True,
        "repository_count": report.repository_count,
        "stale_count": report.stale_count,
        "recent_backup_count": report.recent_backup_count,
        "sent_at": serialize_datetime(now_naive),
    }


async def run_backup_monitoring_and_reports(
    db: Session, now: Optional[datetime] = None
) -> dict:
    now_naive = _normalize_now(now)
    monitoring_result = await run_backup_monitoring(db, now_naive)
    settings = _get_or_create_settings(db)
    report_result = {"sent": False, "reason": "not_due", "repository_count": 0}
    if is_report_due(settings, now_naive):
        report_result = await send_backup_report_now(db, now_naive, force=True)
    return {"monitoring": monitoring_result, "report": report_result}
