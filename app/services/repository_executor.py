from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime
from typing import Any, Callable, Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.database.models import AgentJob, AgentMachine, BackupJob, Repository
from app.services.job_admission import (
    OPERATION_BACKUP,
    ensure_repository_admission,
    ignore_active_job,
    operation_for_agent_job_kind,
)

EXECUTOR_SERVER = "server"
EXECUTOR_AGENT = "agent"
TERMINAL_AGENT_STATUSES = {"completed", "failed", "canceled"}
REPOSITORY_OPERATION_CAPABILITIES = {
    "repository.init",
    "repository.info",
    "repository.list_archives",
    "repository.list_archive_contents",
    "repository.extract_archive_file",
    "repository.restore",
    "repository.check",
    "repository.prune",
    "repository.compact",
    "repository.rclone_sync",
}


def normalize_executor_type(
    value: Optional[str], *, execution_target: Optional[str] = None
) -> str:
    executor_type = (value or "").strip().lower()
    if not executor_type:
        legacy_target = (execution_target or "local").strip().lower()
        executor_type = EXECUTOR_AGENT if legacy_target == "agent" else EXECUTOR_SERVER
    if executor_type not in {EXECUTOR_SERVER, EXECUTOR_AGENT}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"key": "backend.errors.repo.invalidExecutorType"},
        )
    return executor_type


def repository_executor_type(repository: Repository) -> str:
    return normalize_executor_type(
        getattr(repository, "executor_type", None),
        execution_target=getattr(repository, "execution_target", None),
    )


def is_agent_executor(repository: Repository) -> bool:
    return repository_executor_type(repository) == EXECUTOR_AGENT


def legacy_execution_target(
    *, executor_type: str, repository_location: Optional[str] = None
) -> str:
    if executor_type == EXECUTOR_AGENT:
        return "agent"
    location = (repository_location or "local").strip().lower()
    return "ssh" if location == "ssh" else "local"


def decode_json_list(value: Any) -> list:
    if not value:
        return []
    if isinstance(value, list):
        return value
    try:
        decoded = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return []
    return decoded if isinstance(decoded, list) else []


def _agent_source_paths(
    *,
    source_directories: Optional[list[str]],
    source_locations: Optional[list[dict[str, Any]]],
    repository: Repository,
) -> list[str]:
    if source_locations:
        paths: list[str] = []
        for location in source_locations:
            if not isinstance(location, dict):
                continue
            source_type = location.get("source_type", "local")
            if source_type == "agent":
                if int(location.get("agent_machine_id") or 0) != int(
                    repository.agent_machine_id or 0
                ):
                    raise ValueError("Agent execution requires same-agent source paths")
            elif source_type != "local":
                raise ValueError("Agent execution requires local source paths")
            paths.extend(
                path
                for path in location.get("paths") or []
                if isinstance(path, str) and path.strip()
            )
        return paths
    if source_directories is not None:
        return source_directories
    return decode_json_list(repository.source_directories)


def build_agent_backup_payload(
    repository: Repository,
    archive_name: str,
    *,
    source_directories: Optional[list[str]] = None,
    source_locations: Optional[list[dict[str, Any]]] = None,
    exclude_patterns: Optional[list[str]] = None,
    compression: Optional[str] = None,
    custom_flags: Optional[str] = None,
    upload_ratelimit_kib: Optional[int] = None,
) -> dict[str, Any]:
    source_paths = _agent_source_paths(
        source_directories=source_directories,
        source_locations=source_locations,
        repository=repository,
    )
    repository_payload = {
        "id": repository.id,
        "path": repository.path,
        "borg_version": repository.borg_version or 1,
    }
    if repository.remote_path:
        repository_payload["remote_path"] = repository.remote_path

    backup_payload: dict[str, Any] = {
        "archive_name": archive_name,
        "source_paths": source_paths,
        "compression": compression or repository.compression or "lz4",
        "exclude_patterns": exclude_patterns
        if exclude_patterns is not None
        else decode_json_list(repository.exclude_patterns),
        "custom_flags": custom_flags
        if custom_flags is not None
        else repository.custom_flags or "",
    }
    effective_upload_ratelimit_kib = (
        upload_ratelimit_kib
        if upload_ratelimit_kib is not None
        else getattr(repository, "upload_ratelimit_kib", None)
    )
    if effective_upload_ratelimit_kib:
        backup_payload["upload_ratelimit_kib"] = effective_upload_ratelimit_kib

    secrets = {}
    if repository.passphrase:
        secrets["BORG_PASSPHRASE"] = {"value": repository.passphrase}

    return {
        "schema_version": 1,
        "job_kind": "backup.create",
        "repository": repository_payload,
        "backup": backup_payload,
        "secrets": secrets,
    }


def build_agent_repository_operation_payload(
    repository: Repository,
    job_kind: str,
    *,
    operation: Optional[dict[str, Any]] = None,
    maintenance_job_kind: Optional[str] = None,
    maintenance_job_id: Optional[int] = None,
) -> dict[str, Any]:
    if job_kind not in REPOSITORY_OPERATION_CAPABILITIES:
        raise ValueError(f"Unsupported repository operation: {job_kind}")

    repository_payload = {
        "id": repository.id,
        "path": repository.path,
        "borg_version": repository.borg_version or 1,
    }
    if repository.remote_path:
        repository_payload["remote_path"] = repository.remote_path

    operation_payload = dict(operation or {})
    if maintenance_job_kind and maintenance_job_id:
        operation_payload["maintenance_job"] = {
            "kind": maintenance_job_kind,
            "id": maintenance_job_id,
        }

    secrets = {}
    if repository.passphrase:
        secrets["BORG_PASSPHRASE"] = {"value": repository.passphrase}

    return {
        "schema_version": 1,
        "job_kind": job_kind,
        "repository": repository_payload,
        "operation": operation_payload,
        "secrets": secrets,
    }


def validate_agent_backup_repository(
    db: Session, repository: Repository, *, source_paths: Optional[list[str]] = None
) -> AgentMachine:
    if repository.mode == "observe":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"key": "backend.errors.repo.cannotBackupObserveRepository"},
        )
    if not repository.agent_machine_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"key": "backend.errors.agents.agentRequired"},
        )

    agent = (
        db.query(AgentMachine)
        .filter(AgentMachine.id == repository.agent_machine_id)
        .first()
    )
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"key": "backend.errors.agents.agentNotFound"},
        )
    if agent.status in ("disabled", "revoked"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"key": "backend.errors.agents.agentNotQueueable"},
        )
    using_repository_sources = source_paths is None
    if using_repository_sources:
        source_paths = decode_json_list(repository.source_directories)
    if not source_paths:
        detail_key = (
            "backend.errors.repo.agentManualBackupRequiresPlanSources"
            if using_repository_sources
            else "backend.errors.repo.atLeastOneSourceDirRequired"
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"key": detail_key},
        )
    return agent


def validate_agent_repository_operation(
    db: Session, repository: Repository, *, job_kind: str
) -> AgentMachine:
    if not is_agent_executor(repository):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"key": "backend.errors.repo.agentRepositoryRequired"},
        )
    if job_kind not in REPOSITORY_OPERATION_CAPABILITIES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"key": "backend.errors.agents.unsupportedJobKind"},
        )
    if not repository.agent_machine_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"key": "backend.errors.agents.agentRequired"},
        )

    agent = (
        db.query(AgentMachine)
        .filter(AgentMachine.id == repository.agent_machine_id)
        .first()
    )
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"key": "backend.errors.agents.agentNotFound"},
        )
    if agent.status in ("disabled", "revoked"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"key": "backend.errors.agents.agentNotQueueable"},
        )
    capabilities = agent.capabilities or []
    if job_kind not in capabilities:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "key": "backend.errors.agents.capabilityMissing",
                "params": {"capability": job_kind},
            },
        )
    return agent


def queue_agent_repository_operation_job(
    db: Session,
    repository: Repository,
    *,
    job_kind: str,
    operation: Optional[dict[str, Any]] = None,
    maintenance_job_kind: Optional[str] = None,
    maintenance_job_id: Optional[int] = None,
) -> AgentJob:
    agent = validate_agent_repository_operation(db, repository, job_kind=job_kind)
    operation_payload = operation
    admission_operation = operation_for_agent_job_kind(job_kind)
    maintenance_table_by_kind = {
        "check": "check_jobs",
        "restore_check": "restore_check_jobs",
        "compact": "compact_jobs",
        "prune": "prune_jobs",
    }
    ensure_repository_admission(
        db,
        repository,
        admission_operation,
        ignore=ignore_active_job(
            maintenance_table_by_kind.get(maintenance_job_kind or ""),
            maintenance_job_id,
        ),
    )
    now = datetime.utcnow()
    agent_job = AgentJob(
        agent_machine_id=agent.id,
        job_type="repository",
        status="queued",
        payload=build_agent_repository_operation_payload(
            repository,
            job_kind,
            operation=operation_payload,
            maintenance_job_kind=maintenance_job_kind,
            maintenance_job_id=maintenance_job_id,
        ),
        created_at=now,
        updated_at=now,
    )
    db.add(agent_job)
    db.commit()
    db.refresh(agent_job)
    return agent_job


async def wait_for_agent_repository_operation_job(
    db: Session,
    agent_job_id: int,
    *,
    timeout_seconds: int = 15,
    poll_interval_seconds: float = 0.25,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        db.expire_all()
        agent_job = db.query(AgentJob).filter(AgentJob.id == agent_job_id).first()
        if not agent_job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"key": "backend.errors.agents.jobNotFound"},
            )
        if agent_job.status == "completed":
            return agent_job.result or {}
        if agent_job.status in TERMINAL_AGENT_STATUSES:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={
                    "key": "backend.errors.agents.repositoryOperationFailed",
                    "message": agent_job.error_message,
                },
            )
        await asyncio.sleep(poll_interval_seconds)

    raise HTTPException(
        status_code=status.HTTP_504_GATEWAY_TIMEOUT,
        detail={"key": "backend.errors.agents.repositoryOperationTimeout"},
    )


def queue_agent_backup_job(
    db: Session,
    backup_job: BackupJob,
    repository: Repository,
    *,
    archive_name: Optional[str] = None,
    source_directories: Optional[list[str]] = None,
    source_locations: Optional[list[dict[str, Any]]] = None,
    exclude_patterns: Optional[list[str]] = None,
    compression: Optional[str] = None,
    custom_flags: Optional[str] = None,
    upload_ratelimit_kib: Optional[int] = None,
) -> AgentJob:
    source_paths = _agent_source_paths(
        source_directories=source_directories,
        source_locations=source_locations,
        repository=repository,
    )
    agent = validate_agent_backup_repository(db, repository, source_paths=source_paths)
    ensure_repository_admission(
        db,
        repository,
        OPERATION_BACKUP,
        ignore=ignore_active_job(BackupJob.__tablename__, backup_job.id),
    )

    archive_name = archive_name or (
        f"manual-backup-{datetime.now().strftime('%Y-%m-%dT%H:%M:%S')}"
    )
    backup_job.execution_mode = EXECUTOR_AGENT
    backup_job.archive_name = archive_name

    now = datetime.utcnow()
    agent_job = AgentJob(
        agent_machine_id=agent.id,
        backup_job_id=backup_job.id,
        job_type="backup",
        status="queued",
        payload=build_agent_backup_payload(
            repository,
            archive_name,
            source_directories=source_paths,
            exclude_patterns=exclude_patterns,
            compression=compression,
            custom_flags=custom_flags,
            upload_ratelimit_kib=upload_ratelimit_kib,
        ),
        created_at=now,
        updated_at=now,
    )
    db.add(agent_job)
    db.commit()
    db.refresh(agent_job)
    return agent_job


def get_agent_job_for_backup(db: Session, backup_job_id: int) -> Optional[AgentJob]:
    return (
        db.query(AgentJob)
        .filter(AgentJob.backup_job_id == backup_job_id)
        .order_by(AgentJob.id.desc())
        .first()
    )


def cancel_agent_backup_job(
    db: Session, backup_job: BackupJob, *, now: Optional[datetime] = None
) -> tuple[AgentJob, bool]:
    agent_job = get_agent_job_for_backup(db, backup_job.id)
    if not agent_job:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"key": "backend.errors.backup.canOnlyCancelRunningJobs"},
        )

    now = now or datetime.utcnow()
    if agent_job.status == "queued":
        agent_job.status = "canceled"
        agent_job.completed_at = now
        backup_job.status = "cancelled"
        backup_job.completed_at = now
    elif agent_job.status in ("claimed", "running", "cancel_requested"):
        agent_job.status = "cancel_requested"
        backup_job.status = "running"
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"key": "backend.errors.backup.canOnlyCancelRunningJobs"},
        )
    agent_job.updated_at = now
    return agent_job, False


async def wait_for_agent_backup_job(
    db: Session,
    agent_job_id: int,
    backup_job_id: int,
    is_cancelled: Callable[[], bool],
    *,
    poll_interval_seconds: float = 0.5,
) -> str:
    while True:
        db.expire_all()
        agent_job = db.query(AgentJob).filter(AgentJob.id == agent_job_id).first()
        backup_job = db.query(BackupJob).filter(BackupJob.id == backup_job_id).first()
        if not agent_job or not backup_job:
            return "failed"

        if is_cancelled() and agent_job.status not in TERMINAL_AGENT_STATUSES:
            cancel_agent_backup_job(db, backup_job)
            db.commit()

        if agent_job.status in TERMINAL_AGENT_STATUSES:
            return backup_job.status or (
                "cancelled" if agent_job.status == "canceled" else agent_job.status
            )

        await asyncio.sleep(poll_interval_seconds)
