import asyncio
import os
from datetime import datetime
from typing import Any, Awaitable, Callable, Optional, Type

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.security import check_repo_access
from app.database.models import Repository, User
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


def ensure_no_running_job(
    db: Session,
    job_model: Type[Any],
    repository_id: int,
    *,
    error_key: str,
) -> None:
    running_job = (
        db.query(job_model)
        .filter(
            job_model.repository_id == repository_id,
            job_model.status == "running",
        )
        .first()
    )
    if running_job:
        raise HTTPException(status_code=409, detail={"key": error_key})


def create_maintenance_job(
    db: Session,
    job_model: Type[Any],
    repository: Repository,
    *,
    status: str = "pending",
    extra_fields: Optional[dict[str, Any]] = None,
):
    payload = {
        "repository_id": repository.id,
        "repository_path": repository.path,
        "status": status,
    }
    if extra_fields:
        payload.update(extra_fields)

    job = job_model(**payload)
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def create_running_maintenance_job(
    db: Session,
    job_model: Type[Any],
    repository: Repository,
):
    return create_maintenance_job(
        db,
        job_model,
        repository,
        status="running",
        extra_fields={
            "started_at": datetime.utcnow(),
            "progress": 0,
        },
    )


def schedule_background_job(coro) -> None:
    asyncio.create_task(coro)


def create_started_maintenance_job(
    db: Session,
    job_model: Type[Any],
    repository: Repository,
    *,
    status: str = "pending",
    extra_fields: Optional[dict[str, Any]] = None,
):
    payload = dict(extra_fields or {})
    if status == "running":
        payload.setdefault("started_at", datetime.utcnow())
        payload.setdefault("progress", 0)
    return create_maintenance_job(
        db,
        job_model,
        repository,
        status=status,
        extra_fields=payload or None,
    )


def start_background_maintenance_job(
    db: Session,
    repository: Repository,
    job_model: Type[Any],
    *,
    error_key: str,
    dispatcher: Callable[[Any], Awaitable[Any]],
    status: str = "pending",
    extra_fields: Optional[dict[str, Any]] = None,
):
    ensure_no_running_job(
        db,
        job_model,
        repository.id,
        error_key=error_key,
    )
    job = create_started_maintenance_job(
        db,
        job_model,
        repository,
        status=status,
        extra_fields=extra_fields,
    )
    schedule_background_job(dispatcher(job))
    return job


def get_job_with_repository(
    db: Session,
    current_user: User,
    job_model: Type[Any],
    job_id: int,
    *,
    not_found_key: str,
    required_role: str = "viewer",
):
    job = db.query(job_model).filter(job_model.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail={"key": not_found_key})

    repository = db.query(Repository).filter(Repository.id == job.repository_id).first()
    if not repository:
        raise HTTPException(
            status_code=404, detail={"key": "backend.errors.repo.repositoryNotFound"}
        )

    check_repo_access(db, current_user, repository, required_role)
    return job, repository


def get_repository_jobs(
    db: Session,
    current_user: User,
    repo_id: int,
    job_model: Type[Any],
    *,
    limit: int = 10,
    required_role: str = "viewer",
) -> list[Any]:
    repository = get_repository_with_access_or_empty(
        db,
        current_user,
        repo_id,
        required_role=required_role,
    )
    if not repository:
        return []

    return (
        db.query(job_model)
        .filter(job_model.repository_id == repo_id)
        .order_by(job_model.id.desc())
        .limit(limit)
        .all()
    )


def read_job_logs(job: Any, *, fallback_to_logs: bool = True) -> str:
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
        payload["logs"] = read_job_logs(job, fallback_to_logs=fallback_to_logs)
    if include_has_logs:
        payload["has_logs"] = bool(getattr(job, "has_logs", False))
    return payload


def serialize_job_summary(
    job: Any,
    *,
    include_progress: bool = False,
    include_has_logs: bool = False,
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
        payload["has_logs"] = bool(getattr(job, "has_logs", False))
    return payload
