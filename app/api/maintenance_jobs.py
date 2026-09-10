import os
from typing import Any, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.security import check_repo_access
from app.database.models import Repository, User
from app.services.log_policy import DEFAULT_LOG_SAVE_POLICY, job_has_logs_by_policy
from app.utils.datetime_utils import serialize_datetime


def get_repository_with_access(
    db: Session,
    current_user: User,
    repo_id: int,
    *,
    required_role: str = "viewer",
) -> Repository:
    repository = db.query(Repository).filter(Repository.id == repo_id).first()
    if not repository:
        raise HTTPException(
            status_code=404, detail={"key": "backend.errors.repo.repositoryNotFound"}
        )
    check_repo_access(db, current_user, repository, required_role)
    return repository


def get_repository_with_access_or_empty(
    db: Session,
    current_user: User,
    repo_id: int,
    *,
    required_role: str = "viewer",
) -> Optional[Repository]:
    repository = db.query(Repository).filter(Repository.id == repo_id).first()
    if not repository:
        return None
    check_repo_access(db, current_user, repository, required_role)
    return repository


def get_maintenance_job_with_repository(
    db: Session,
    current_user: User,
    kind: str,
    job_id: int,
    *,
    not_found_key: str,
    required_role: str = "viewer",
):
    """Resolve a maintenance job id to its operation."""
    from app.services.operations.job_facade import resolve_maintenance_job

    job = resolve_maintenance_job(db, job_id, kind)
    if job is None:
        raise HTTPException(status_code=404, detail={"key": not_found_key})

    repository = db.query(Repository).filter(Repository.id == job.repository_id).first()
    if not repository:
        raise HTTPException(
            status_code=404, detail={"key": "backend.errors.repo.repositoryNotFound"}
        )

    check_repo_access(db, current_user, repository, required_role)
    return job, repository


def get_repository_maintenance_jobs(
    db: Session,
    current_user: User,
    repo_id: int,
    kind: str,
    *,
    limit: int = 10,
    required_role: str = "viewer",
) -> list[Any]:
    """The newest operations of this kind on the repository, newest first."""
    from app.database.models import Operation
    from app.services.operations.job_facade import MaintenanceJobFacade

    repository = get_repository_with_access_or_empty(
        db, current_user, repo_id, required_role=required_role
    )
    if not repository:
        return []

    operations = (
        db.query(Operation)
        .filter(Operation.repository_id == repo_id, Operation.kind == kind)
        .order_by(Operation.id.desc())
        .limit(limit)
        .all()
    )
    return [MaintenanceJobFacade(db, op) for op in operations]


def job_has_logs_for_policy(
    job: Any, *, log_save_policy: str = DEFAULT_LOG_SAVE_POLICY
) -> bool:
    return job_has_logs_by_policy(
        job,
        log_save_policy,
        output_text=[
            getattr(job, "logs", None),
            getattr(job, "error_message", None),
        ],
        file_path=getattr(job, "log_file_path", None),
    )


def read_job_logs(
    job: Any,
    *,
    fallback_to_logs: bool = True,
    log_save_policy: str = DEFAULT_LOG_SAVE_POLICY,
) -> str:
    if not job_has_logs_for_policy(job, log_save_policy=log_save_policy):
        return ""

    log_file_path = getattr(job, "log_file_path", None)
    if log_file_path and os.path.exists(log_file_path):
        try:
            with open(log_file_path, "r") as handle:
                return handle.read()
        except Exception as exc:
            return f"Failed to read log file: {exc}"

    if fallback_to_logs:
        return getattr(job, "logs", "") or ""
    return ""


def serialize_job_status(
    job: Any,
    *,
    include_progress: bool = False,
    include_logs: bool = False,
    include_has_logs: bool = False,
    fallback_to_logs: bool = True,
    log_save_policy: str = DEFAULT_LOG_SAVE_POLICY,
) -> dict[str, Any]:
    payload = {
        "id": job.id,
        "repository_id": job.repository_id,
        "status": job.status,
        "started_at": serialize_datetime(job.started_at),
        "completed_at": serialize_datetime(job.completed_at),
        "error_message": job.error_message,
    }
    if include_progress:
        payload["progress"] = getattr(job, "progress", None)
        payload["progress_message"] = getattr(job, "progress_message", None)
    if include_logs:
        payload["logs"] = read_job_logs(
            job,
            fallback_to_logs=fallback_to_logs,
            log_save_policy=log_save_policy,
        )
    if include_has_logs:
        payload["has_logs"] = job_has_logs_for_policy(
            job, log_save_policy=log_save_policy
        )
    # Compact only: `borg compact --stats` output (Borg 2). The facade would
    # hand back a `stats` key of any kind's result; keep the contract narrow.
    if getattr(job, "kind", None) == "compact":
        stats = getattr(job, "stats", None)
        if stats is not None:
            payload["stats"] = stats
    return payload


def serialize_job_summary(
    job: Any,
    *,
    include_progress: bool = False,
    include_has_logs: bool = False,
    log_save_policy: str = DEFAULT_LOG_SAVE_POLICY,
) -> dict[str, Any]:
    payload = {
        "id": job.id,
        "repository_id": job.repository_id,
        "status": job.status,
        "started_at": serialize_datetime(job.started_at),
        "completed_at": serialize_datetime(job.completed_at),
        "error_message": job.error_message,
    }
    if include_progress:
        payload["progress"] = getattr(job, "progress", None)
        payload["progress_message"] = getattr(job, "progress_message", None)
    if include_has_logs:
        payload["has_logs"] = job_has_logs_for_policy(
            job, log_save_policy=log_save_policy
        )
    return payload
