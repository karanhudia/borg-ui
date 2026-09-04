"""Series inference (spec section 6.6).

Borg 2 names a series directly. For Borg 1 the series is the literal prefix
of a schedule or plan archive name template that targets the repository,
else the archive name with a trailing timestamp stripped, else "default".
"""

import re
from typing import Optional, Sequence

from sqlalchemy.orm import Session

from app.database.models import (
    BackupPlan,
    BackupPlanRepository,
    Repository,
    ScheduledJob,
    ScheduledJobRepository,
)
from app.utils.archive_names import build_archive_name

DEFAULT_SERIES = "default"

_TIMESTAMP_SUFFIXES = (
    # 2026-09-02T02:00:00, 2026-09-02_02-00-00, 2026-09-02 02:00:00,
    # optional fraction and zone offset
    re.compile(
        r"[-_.]?\d{4}-\d{2}-\d{2}[T_ -]\d{2}[:\-.]?\d{2}[:\-.]?\d{2}"
        r"(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?$"
    ),
    # 20260902T020000, 20260902_020000, 20260902-020000
    re.compile(r"[-_.]?\d{8}[T_-]?\d{6}$"),
    # 2026-09-02
    re.compile(r"[-_.]?\d{4}-\d{2}-\d{2}$"),
    # unix epoch seconds
    re.compile(r"[-_.]?\d{10}$"),
)


def strip_timestamp(name: str) -> Optional[str]:
    """Return the name without its trailing timestamp, or None when there is
    no timestamp or nothing would remain."""
    for pattern in _TIMESTAMP_SUFFIXES:
        stripped = pattern.sub("", name, count=1)
        if stripped != name:
            return stripped.rstrip("-_.") or None
    return None


def template_prefix(
    template: Optional[str], *, job_name: str, repo_name: Optional[str]
) -> Optional[str]:
    """The literal prefix backups from this template share: the template
    rendered with its time placeholders removed. Without a template the
    default name builder applies, so the prefix is job (and repo) name."""
    prefix = build_archive_name(
        job_name, repo_name, template, timestamp="", stable_series=True
    )
    return prefix or None


def _schedules_for(db: Session, repository: Repository) -> list[ScheduledJob]:
    direct = (
        db.query(ScheduledJob).filter(ScheduledJob.repository_id == repository.id).all()
    )
    linked_ids = [
        row.scheduled_job_id
        for row in db.query(ScheduledJobRepository.scheduled_job_id)
        .filter(ScheduledJobRepository.repository_id == repository.id)
        .all()
    ]
    linked = (
        db.query(ScheduledJob).filter(ScheduledJob.id.in_(linked_ids)).all()
        if linked_ids
        else []
    )
    seen: set[int] = set()
    result = []
    for job in direct + linked:
        if job.id not in seen:
            seen.add(job.id)
            result.append(job)
    return result


def _plans_for(db: Session, repository: Repository) -> list[BackupPlan]:
    plan_ids = [
        row.backup_plan_id
        for row in db.query(BackupPlanRepository.backup_plan_id)
        .filter(BackupPlanRepository.repository_id == repository.id)
        .all()
    ]
    if not plan_ids:
        return []
    return db.query(BackupPlan).filter(BackupPlan.id.in_(plan_ids)).all()


def series_prefixes_for_repository(db: Session, repository: Repository) -> list[str]:
    """Template prefixes of every schedule and plan targeting the repository,
    longest first so "nas-docs" wins over "nas"."""
    prefixes: set[str] = set()
    for job in _schedules_for(db, repository):
        prefix = template_prefix(
            job.archive_name_template, job_name=job.name, repo_name=repository.name
        )
        if prefix:
            prefixes.add(prefix)
    for plan in _plans_for(db, repository):
        prefix = template_prefix(
            plan.archive_name_template, job_name=plan.name, repo_name=repository.name
        )
        if prefix:
            prefixes.add(prefix)
    return sorted(prefixes, key=len, reverse=True)


def cron_for_repository(
    db: Session, repository: Repository
) -> tuple[Optional[str], Optional[str]]:
    """Cron expression and timezone of the first enabled cron schedule that
    targets the repository, for the missed-run rule (spec 9.5)."""
    for job in _schedules_for(db, repository):
        if job.enabled and job.schedule_mode == "cron" and job.cron_expression:
            return job.cron_expression, job.timezone
    return None, None


def infer_series(name: str, borg_version: int, prefixes: Sequence[str] = ()) -> str:
    if borg_version == 2:
        return name
    # Sort here rather than trust caller order, so the longest (most
    # specific) matching prefix always wins regardless of how it was
    # passed in.
    for prefix in sorted(prefixes, key=len, reverse=True):
        if name == prefix or name.startswith(prefix + "-"):
            return prefix
    stripped = strip_timestamp(name)
    if stripped:
        return stripped
    return DEFAULT_SERIES
