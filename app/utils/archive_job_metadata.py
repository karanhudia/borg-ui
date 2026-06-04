"""Attach backup job metadata to archive-list responses."""

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.database.models import BackupJob, BackupPlanRun, Repository


def _archive_name(archive: Any) -> Optional[str]:
    if not isinstance(archive, dict):
        return None

    name = archive.get("name") or archive.get("archive")
    return name if isinstance(name, str) and name else None


def _coerce_naive_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _parse_archive_time(archive: dict) -> Optional[datetime]:
    value = archive.get("start") or archive.get("time")
    if isinstance(value, datetime):
        return _coerce_naive_utc(value)
    if not isinstance(value, str) or not value:
        return None

    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return _coerce_naive_utc(parsed)


def _job_times(job: BackupJob) -> list[datetime]:
    times = []
    for value in (job.started_at, job.completed_at, job.created_at):
        if isinstance(value, datetime):
            times.append(_coerce_naive_utc(value))
    return times


def _select_job_for_archive(
    jobs: list[BackupJob], archive_time: Optional[datetime]
) -> Optional[BackupJob]:
    if not jobs:
        return None
    if archive_time is None:
        return jobs[0]

    def sort_key(job: BackupJob) -> tuple[float, int]:
        times = _job_times(job)
        if not times:
            return (float("inf"), -(job.id or 0))
        closest_seconds = min(
            abs((time - archive_time).total_seconds()) for time in times
        )
        return (closest_seconds, -(job.id or 0))

    return min(jobs, key=sort_key)


def _trigger_for_job(job: BackupJob, plan_runs_by_id: dict[int, BackupPlanRun]) -> str:
    if job.backup_plan_run_id:
        plan_run = plan_runs_by_id.get(job.backup_plan_run_id)
        if plan_run and plan_run.trigger:
            return plan_run.trigger
        return "manual"
    if job.scheduled_job_id:
        return "schedule"
    return "manual"


def enrich_archives_with_backup_metadata(
    archives: list[Any], repository: Repository, db: Session
) -> list[Any]:
    """Return archives enriched with trigger/source metadata from backup jobs."""
    archive_names = {name for archive in archives if (name := _archive_name(archive))}
    if not archive_names:
        return archives

    repository_filters = []
    if getattr(repository, "id", None) is not None:
        repository_filters.append(BackupJob.repository_id == repository.id)
    if getattr(repository, "path", None):
        repository_filters.append(BackupJob.repository == repository.path)

    query = db.query(BackupJob).filter(BackupJob.archive_name.in_(archive_names))
    if repository_filters:
        query = query.filter(or_(*repository_filters))

    jobs = query.order_by(BackupJob.id.desc()).all()
    if not jobs:
        return archives

    plan_run_ids = {job.backup_plan_run_id for job in jobs if job.backup_plan_run_id}
    plan_runs_by_id = {}
    if plan_run_ids:
        plan_runs_by_id = {
            plan_run.id: plan_run
            for plan_run in db.query(BackupPlanRun)
            .filter(BackupPlanRun.id.in_(plan_run_ids))
            .all()
        }

    jobs_by_archive_name = defaultdict(list)
    for job in jobs:
        jobs_by_archive_name[job.archive_name].append(job)

    enriched_archives = []
    for archive in archives:
        name = _archive_name(archive)
        if not isinstance(archive, dict) or not name:
            enriched_archives.append(archive)
            continue

        job = _select_job_for_archive(
            jobs_by_archive_name.get(name, []), _parse_archive_time(archive)
        )
        if not job:
            enriched_archives.append(archive)
            continue

        enriched = dict(archive)
        enriched["triggered_by"] = _trigger_for_job(job, plan_runs_by_id)
        enriched["backup_job_id"] = job.id
        enriched["backup_plan_id"] = job.backup_plan_id
        enriched["backup_plan_run_id"] = job.backup_plan_run_id
        enriched["scheduled_job_id"] = job.scheduled_job_id
        enriched_archives.append(enriched)

    return enriched_archives
