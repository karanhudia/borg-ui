"""Borg 2 backup operation endpoints — mounted at /api/v2/backup/

Handles create, prune, compact, and check for Borg 2 repositories.
Compact is a first-class operation in Borg 2 (not optional — space is never
freed automatically after delete or prune).
"""

import json

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional
import structlog

from app.database.database import get_db
from app.database.models import User, Repository, CheckJob, CompactJob, BackupJob
from app.api.maintenance_jobs import (
    get_repository_with_access,
    start_background_maintenance_job,
)
from app.core.security import get_current_user
from app.core.features import require_feature
from app.core.borg_router import BorgRouter
from app.services.backup_service import backup_service
from app.services.v2.check_service import check_v2_service
from app.services.v2.compact_service import compact_v2_service
from app.services.v2.prune_service import prune_v2_service

logger = structlog.get_logger()
router = APIRouter(tags=["Backup v2"], dependencies=[require_feature("borg_v2")])


# ── Schemas ────────────────────────────────────────────────────────────────────


class BackupV2Request(BaseModel):
    repository_id: int
    archive_name: Optional[str] = None


class PruneV2Request(BaseModel):
    repository_id: int
    keep_hourly: int = 0
    keep_daily: int = 7
    keep_weekly: int = 4
    keep_monthly: int = 6
    keep_quarterly: int = 0
    keep_yearly: int = 1
    dry_run: bool = False


class CompactV2Request(BaseModel):
    repository_id: int


class CheckV2Request(BaseModel):
    repository_id: int
    max_duration: Optional[int] = None


# ── Helpers ────────────────────────────────────────────────────────────────────


def _get_v2_repo_by_id(repo_id: int, db: Session, current_user: User) -> Repository:
    repo = get_repository_with_access(
        db, current_user, repo_id, required_role="operator"
    )
    if repo.borg_version != 2:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"key": "backend.errors.restore.repositoryNotFound"},
        )
    return repo


def _source_dirs(repo: Repository) -> list:
    if not repo.source_directories:
        return []
    try:
        return json.loads(repo.source_directories)
    except (json.JSONDecodeError, TypeError):
        return []


# ── Routes ─────────────────────────────────────────────────────────────────────


@router.post("/run")
async def run_backup(
    data: BackupV2Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a new Borg 2 archive (borg2 create)."""
    repo = _get_v2_repo_by_id(data.repository_id, db, current_user)
    source_dirs = _source_dirs(repo)
    if not source_dirs:
        raise HTTPException(
            status_code=400,
            detail={"key": "backend.errors.backup.noSourceDirectories"},
        )

    backup_job = BackupJob(
        repository=repo.path,
        status="pending",
        source_ssh_connection_id=repo.source_ssh_connection_id,
    )
    db.add(backup_job)
    db.commit()
    db.refresh(backup_job)

    await backup_service.execute_backup(
        backup_job.id,
        repo.path,
        db=db,
        archive_name=data.archive_name,
    )
    db.refresh(backup_job)

    if backup_job.status not in {"completed", "completed_with_warnings"}:
        raise HTTPException(
            status_code=500,
            detail={
                "key": "backend.errors.backup.failed",
                "params": {"error": backup_job.error_message or "Backup failed"},
            },
        )

    return {
        "success": True,
        "stats": {
            "original_size": backup_job.original_size or 0,
            "compressed_size": backup_job.compressed_size or 0,
            "deduplicated_size": backup_job.deduplicated_size or 0,
            "nfiles": backup_job.nfiles or 0,
        },
        "status": backup_job.status,
        "job_id": backup_job.id,
    }


@router.post("/prune")
async def prune_archives(
    data: PruneV2Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Prune old Borg 2 archives.

    Note: after pruning, space is not freed until compact() is called.
    """
    if not current_user.is_admin:
        raise HTTPException(
            status_code=403, detail={"key": "backend.errors.repo.adminAccessRequired"}
        )

    repo = _get_v2_repo_by_id(data.repository_id, db, current_user)
    result = await prune_v2_service.run_prune(
        repo=repo,
        keep_hourly=data.keep_hourly,
        keep_daily=data.keep_daily,
        keep_weekly=data.keep_weekly,
        keep_monthly=data.keep_monthly,
        keep_quarterly=data.keep_quarterly,
        keep_yearly=data.keep_yearly,
        dry_run=data.dry_run,
    )

    if not result["success"]:
        raise HTTPException(
            status_code=500,
            detail={
                "key": "backend.errors.prune.failed",
                "params": {"error": result["stderr"]},
            },
        )

    stdout = result.get("stdout", "") or ""
    if not data.dry_run:
        note = "Run compact to reclaim freed space"
        stdout = "\n\n".join(part for part in [stdout, note] if part)
        await BorgRouter(repo).update_stats(db)

    return {
        "success": True,
        "dry_run": data.dry_run,
        "prune_result": {
            "success": True,
            "stdout": stdout,
            "stderr": result.get("stderr", "") or "",
        },
    }


@router.post("/compact")
async def compact_repository(
    data: CompactV2Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Compact a Borg 2 repository to reclaim disk space (non-blocking).

    Creates a CompactJob record so the frontend can poll progress via the existing
    GET /repositories/{id}/running-jobs endpoint — no frontend changes required.
    """
    if not current_user.is_admin:
        raise HTTPException(
            status_code=403, detail={"key": "backend.errors.repo.adminAccessRequired"}
        )

    repo = _get_v2_repo_by_id(data.repository_id, db, current_user)

    compact_job = start_background_maintenance_job(
        db,
        repo,
        CompactJob,
        error_key="backend.errors.compact.alreadyRunning",
        dispatcher=lambda job: compact_v2_service.execute_compact(job.id, repo.id),
        status="running",
    )

    logger.info(
        "Borg2 compact job created",
        job_id=compact_job.id,
        repository_id=repo.id,
        user=current_user.username,
    )

    return {
        "job_id": compact_job.id,
        "status": "running",
        "message": "backend.success.repo.compactJobStarted",
    }


@router.post("/check")
async def check_repository(
    data: CheckV2Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Start a Borg 2 repository integrity check (non-blocking).

    Creates a CheckJob record so the frontend can poll progress via the existing
    GET /repositories/check-jobs/{job_id} and GET /repositories/{id}/running-jobs
    endpoints — no frontend changes required.
    """
    if not current_user.is_admin:
        raise HTTPException(
            status_code=403, detail={"key": "backend.errors.repo.adminAccessRequired"}
        )

    repo = _get_v2_repo_by_id(data.repository_id, db, current_user)

    check_job = start_background_maintenance_job(
        db,
        repo,
        CheckJob,
        error_key="backend.errors.repo.checkAlreadyRunning",
        dispatcher=lambda job: check_v2_service.execute_check(job.id, repo.id),
        status="running",
        extra_fields={
            "max_duration": data.max_duration,
        },
    )

    logger.info(
        "Borg2 check job created",
        job_id=check_job.id,
        repository_id=repo.id,
        user=current_user.username,
    )

    return {
        "job_id": check_job.id,
        "status": "running",
        "message": "backend.success.repo.checkJobStarted",
    }
