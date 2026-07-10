"""DB-backed admission checks for repository job dispatch."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from fastapi import HTTPException, status
from sqlalchemy import or_, text
from sqlalchemy.orm import Session

from app.database.models import (
    AgentJob,
    BackupJob,
    CheckJob,
    CompactJob,
    DeleteArchiveJob,
    PruneJob,
    Repository,
    RepositoryWipeJob,
    RestoreCheckJob,
    SystemSettings,
)

OPERATION_BACKUP = "backup"
OPERATION_CHECK = "check"
OPERATION_RESTORE = "restore"
OPERATION_RESTORE_CHECK = "restore_check"
OPERATION_COMPACT = "compact"
OPERATION_PRUNE = "prune"
OPERATION_DELETE_ARCHIVE = "delete_archive"
OPERATION_REPOSITORY_WIPE = "repository_wipe"
OPERATION_REPOSITORY_INIT = "repository.init"
OPERATION_REPOSITORY_INFO = "repository.info"
OPERATION_REPOSITORY_LIST_ARCHIVES = "repository.list_archives"
OPERATION_REPOSITORY_LIST_ARCHIVE_CONTENTS = "repository.list_archive_contents"
OPERATION_REPOSITORY_EXTRACT_ARCHIVE_FILE = "repository.extract_archive_file"

OPERATION_CLASS_REPOSITORY_WRITE = "repository_write"
OPERATION_CLASS_REPOSITORY_READ = "repository_read"

DEFAULT_MANUAL_BACKUP_LIMIT = 1
DEFAULT_SCHEDULED_BACKUP_LIMIT = 2

ACTIVE_BACKUP_STATUSES = {"pending", "running"}
ACTIVE_MAINTENANCE_STATUSES = {"pending", "running"}
ACTIVE_AGENT_STATUSES = {"queued", "claimed", "cancel_requested", "running"}
ACTIVE_REPOSITORY_WIPE_STATUSES = {"pending", "running"}

REPOSITORY_OPERATION_ACTIVE_KEY = "backend.errors.jobs.repositoryOperationActive"
MANUAL_BACKUP_LIMIT_KEY = "backend.errors.backup.concurrentLimitReached"

WRITE_OPERATIONS = {
    OPERATION_BACKUP,
    OPERATION_COMPACT,
    OPERATION_PRUNE,
    OPERATION_DELETE_ARCHIVE,
    OPERATION_REPOSITORY_WIPE,
    OPERATION_REPOSITORY_INIT,
}
READ_OPERATIONS = {
    OPERATION_CHECK,
    OPERATION_RESTORE,
    OPERATION_RESTORE_CHECK,
    OPERATION_REPOSITORY_INFO,
    OPERATION_REPOSITORY_LIST_ARCHIVES,
    OPERATION_REPOSITORY_LIST_ARCHIVE_CONTENTS,
    OPERATION_REPOSITORY_EXTRACT_ARCHIVE_FILE,
}

AGENT_JOB_KIND_OPERATIONS = {
    "repository.check": OPERATION_CHECK,
    "repository.prune": OPERATION_PRUNE,
    "repository.compact": OPERATION_COMPACT,
    "repository.init": OPERATION_REPOSITORY_INIT,
    "repository.info": OPERATION_REPOSITORY_INFO,
    "repository.list_archives": OPERATION_REPOSITORY_LIST_ARCHIVES,
    "repository.list_archive_contents": OPERATION_REPOSITORY_LIST_ARCHIVE_CONTENTS,
    "repository.extract_archive_file": OPERATION_REPOSITORY_EXTRACT_ARCHIVE_FILE,
    "repository.restore": OPERATION_RESTORE,
}

MAINTENANCE_MODEL_OPERATIONS = {
    CheckJob: OPERATION_CHECK,
    RestoreCheckJob: OPERATION_RESTORE_CHECK,
    CompactJob: OPERATION_COMPACT,
    PruneJob: OPERATION_PRUNE,
}


@dataclass(frozen=True)
class ActiveRepositoryWork:
    resource_type: str
    resource_id: int
    operation: str
    operation_class: str
    job_table: str
    job_id: int
    status: str


@dataclass(frozen=True)
class IgnoreActiveJob:
    job_table: str
    job_id: int


def operation_class_for(operation: str) -> str:
    if operation in WRITE_OPERATIONS:
        return OPERATION_CLASS_REPOSITORY_WRITE
    if operation in READ_OPERATIONS:
        return OPERATION_CLASS_REPOSITORY_READ
    raise ValueError(f"Unknown repository operation: {operation}")


def operation_for_agent_job_kind(job_kind: str) -> str:
    try:
        return AGENT_JOB_KIND_OPERATIONS[job_kind]
    except KeyError as exc:
        raise ValueError(f"Unsupported agent repository operation: {job_kind}") from exc


def operation_for_maintenance_model(job_model: type[Any]) -> str:
    try:
        return MAINTENANCE_MODEL_OPERATIONS[job_model]
    except KeyError as exc:
        raise ValueError(f"Unsupported maintenance job model: {job_model}") from exc


def ignore_active_job(
    job_table: Optional[str], job_id: Optional[int]
) -> Optional[IgnoreActiveJob]:
    if not job_table or job_id is None:
        return None
    return IgnoreActiveJob(job_table=job_table, job_id=job_id)


def _is_ignored(work: ActiveRepositoryWork, ignore: Optional[IgnoreActiveJob]) -> bool:
    return bool(
        ignore and work.job_table == ignore.job_table and work.job_id == ignore.job_id
    )


def _dialect_name(db: Session) -> str:
    try:
        return db.get_bind().dialect.name
    except Exception:
        return ""


def _lock_repository_scope(db: Session, repository: Repository) -> None:
    if repository.id is None:
        return
    if _dialect_name(db) == "sqlite":
        db.execute(
            text("UPDATE repositories SET id = id WHERE id = :repository_id"),
            {"repository_id": repository.id},
        )
        return
    db.query(Repository).filter(
        Repository.id == repository.id
    ).with_for_update().first()


def lock_backup_capacity_scope(db: Session) -> None:
    """Serialize capacity checks with later job inserts in the transaction."""
    dialect_name = _dialect_name(db)
    if dialect_name == "sqlite":
        db.execute(
            text(
                "UPDATE system_settings SET id = id "
                "WHERE id = (SELECT id FROM system_settings ORDER BY id ASC LIMIT 1)"
            )
        )
        return
    if dialect_name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(:lock_id)"), {"lock_id": 276116})
        return
    db.query(SystemSettings).order_by(SystemSettings.id.asc()).with_for_update().first()


def _repository_backup_filter(repository: Repository):
    filters = [BackupJob.repository == repository.path]
    if repository.id is not None:
        filters.append(BackupJob.repository_id == repository.id)
    return or_(*filters)


def _active_work(
    repository: Repository,
    operation: str,
    job_table: str,
    job: Any,
) -> ActiveRepositoryWork:
    return ActiveRepositoryWork(
        resource_type="repository",
        resource_id=int(repository.id),
        operation=operation,
        operation_class=operation_class_for(operation),
        job_table=job_table,
        job_id=int(job.id),
        status=str(job.status),
    )


def list_active_repository_work(
    db: Session,
    repository: Repository,
    *,
    ignore: Optional[IgnoreActiveJob] = None,
) -> list[ActiveRepositoryWork]:
    """Return persisted active work for a repository grouped by operation class."""
    active: list[ActiveRepositoryWork] = []

    backup_jobs = (
        db.query(BackupJob)
        .filter(
            _repository_backup_filter(repository),
            BackupJob.status.in_(ACTIVE_BACKUP_STATUSES),
        )
        .all()
    )
    active.extend(
        _active_work(repository, OPERATION_BACKUP, BackupJob.__tablename__, job)
        for job in backup_jobs
    )

    maintenance_specs = (
        (CheckJob, OPERATION_CHECK),
        (RestoreCheckJob, OPERATION_RESTORE_CHECK),
        (CompactJob, OPERATION_COMPACT),
        (PruneJob, OPERATION_PRUNE),
        (DeleteArchiveJob, OPERATION_DELETE_ARCHIVE),
    )
    for job_model, operation in maintenance_specs:
        jobs = (
            db.query(job_model)
            .filter(
                job_model.repository_id == repository.id,
                job_model.status.in_(ACTIVE_MAINTENANCE_STATUSES),
            )
            .all()
        )
        active.extend(
            _active_work(repository, operation, job_model.__tablename__, job)
            for job in jobs
        )

    wipe_jobs = (
        db.query(RepositoryWipeJob)
        .filter(
            RepositoryWipeJob.repository_id == repository.id,
            RepositoryWipeJob.status.in_(ACTIVE_REPOSITORY_WIPE_STATUSES),
        )
        .all()
    )
    active.extend(
        _active_work(
            repository,
            OPERATION_REPOSITORY_WIPE,
            RepositoryWipeJob.__tablename__,
            job,
        )
        for job in wipe_jobs
    )

    agent_jobs = (
        db.query(AgentJob)
        .filter(
            AgentJob.job_type == "repository",
            AgentJob.status.in_(ACTIVE_AGENT_STATUSES),
        )
        .all()
    )
    for job in agent_jobs:
        payload = job.payload if isinstance(job.payload, dict) else {}
        repository_payload = payload.get("repository")
        if not isinstance(repository_payload, dict):
            continue
        payload_repo_id = repository_payload.get("id")
        payload_repo_path = repository_payload.get("path")
        if payload_repo_id != repository.id and payload_repo_path != repository.path:
            continue
        job_kind = payload.get("job_kind")
        try:
            operation = operation_for_agent_job_kind(str(job_kind))
        except ValueError:
            continue
        active.append(_active_work(repository, operation, AgentJob.__tablename__, job))

    return [work for work in active if not _is_ignored(work, ignore)]


def _conflict_detail(
    key: str,
    repository: Repository,
    requested_operation: str,
    active: ActiveRepositoryWork,
) -> dict[str, Any]:
    return {
        "key": key,
        "params": {
            "repository_id": repository.id,
            "repository": repository.path,
            "requested_operation": requested_operation,
            "active_operation": active.operation,
            "active_operation_class": active.operation_class,
            "active_job_table": active.job_table,
            "active_job_id": active.job_id,
            "active_status": active.status,
        },
    }


def ensure_repository_admission(
    db: Session,
    repository: Repository,
    operation: str,
    *,
    duplicate_error_key: Optional[str] = None,
    ignore: Optional[IgnoreActiveJob] = None,
) -> None:
    """Reject duplicate or conflicting active work before a job is queued."""
    _lock_repository_scope(db, repository)
    requested_class = operation_class_for(operation)
    active_work = list_active_repository_work(db, repository, ignore=ignore)

    for active in active_work:
        if active.operation == operation:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=_conflict_detail(
                    duplicate_error_key or REPOSITORY_OPERATION_ACTIVE_KEY,
                    repository,
                    operation,
                    active,
                ),
            )

    for active in active_work:
        conflicts = requested_class == OPERATION_CLASS_REPOSITORY_WRITE or (
            requested_class == OPERATION_CLASS_REPOSITORY_READ
            and active.operation_class == OPERATION_CLASS_REPOSITORY_WRITE
        )
        if conflicts:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=_conflict_detail(
                    REPOSITORY_OPERATION_ACTIVE_KEY,
                    repository,
                    operation,
                    active,
                ),
            )


def count_active_manual_backup_jobs(db: Session) -> int:
    return (
        db.query(BackupJob)
        .filter(
            BackupJob.scheduled_job_id.is_(None),
            BackupJob.backup_plan_id.is_(None),
            BackupJob.backup_plan_run_id.is_(None),
            BackupJob.status.in_(ACTIVE_BACKUP_STATUSES),
        )
        .count()
    )


def get_manual_backup_limit(db: Session) -> int:
    settings = db.query(SystemSettings).first()
    if settings and settings.max_concurrent_backups is not None:
        return settings.max_concurrent_backups
    return DEFAULT_MANUAL_BACKUP_LIMIT


def ensure_manual_backup_capacity(db: Session) -> None:
    lock_backup_capacity_scope(db)
    limit = get_manual_backup_limit(db)
    active_count = count_active_manual_backup_jobs(db)
    if limit <= 0 or active_count >= limit:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "key": MANUAL_BACKUP_LIMIT_KEY,
                "params": {"limit": limit, "active": active_count},
            },
        )


def count_active_scheduled_backup_jobs(db: Session) -> int:
    return (
        db.query(BackupJob)
        .filter(
            BackupJob.scheduled_job_id.isnot(None),
            BackupJob.status.in_(ACTIVE_BACKUP_STATUSES),
        )
        .count()
    )


def get_scheduled_backup_limit(db: Session) -> int:
    settings = db.query(SystemSettings).first()
    if settings and settings.max_concurrent_scheduled_backups is not None:
        return settings.max_concurrent_scheduled_backups
    return DEFAULT_SCHEDULED_BACKUP_LIMIT
