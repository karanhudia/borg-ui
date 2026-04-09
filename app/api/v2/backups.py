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
from app.database.models import User, Repository, CheckJob, CompactJob
from app.api.maintenance_jobs import (
    create_running_maintenance_job,
    ensure_no_running_job,
    get_repository_with_access,
    schedule_background_job,
)
from app.core.security import get_current_user
from app.core.features import require_feature
from app.services.v2.check_service import check_v2_service
from app.services.v2.compact_service import compact_v2_service
from app.services.v2.backup_service import backup_v2_service
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


# ── Helpers ────────────────────────────────────────────────────────────────────

def _get_v2_repo_by_id(repo_id: int, db: Session, current_user: User) -> Repository:
    repo = get_repository_with_access(db, current_user, repo_id, required_role="operator")
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

    result = await backup_v2_service.run_backup(
        repo=repo,
        source_paths=source_dirs,
        archive_name=data.archive_name,
    )

    if not result["success"]:
        raise HTTPException(
            status_code=500,
            detail={"key": "backend.errors.backup.failed",
                    "params": {"error": result["stderr"]}},
        )

    try:
        stats = json.loads(result["stdout"])
    except json.JSONDecodeError:
        stats = {}

    return {"success": True, "stats": stats}


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
        raise HTTPException(status_code=403, detail={"key": "backend.errors.repo.adminAccessRequired"})

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
            detail={"key": "backend.errors.prune.failed",
                    "params": {"error": result["stderr"]}},
        )

    return {
        "success": True,
        "output": result["stdout"],
        "note": "Run compact to reclaim freed space" if not data.dry_run else None,
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
        raise HTTPException(status_code=403, detail={"key": "backend.errors.repo.adminAccessRequired"})

    repo = _get_v2_repo_by_id(data.repository_id, db, current_user)

    ensure_no_running_job(
        db,
        CompactJob,
        repo.id,
        error_key="backend.errors.compact.alreadyRunning",
    )

    compact_job = create_running_maintenance_job(db, CompactJob, repo)

    schedule_background_job(compact_v2_service.execute_compact(compact_job.id, repo.id))

    logger.info("Borg2 compact job created", job_id=compact_job.id, repository_id=repo.id,
                user=current_user.username)

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
        raise HTTPException(status_code=403, detail={"key": "backend.errors.repo.adminAccessRequired"})

    repo = _get_v2_repo_by_id(data.repository_id, db, current_user)

    ensure_no_running_job(
        db,
        CheckJob,
        repo.id,
        error_key="backend.errors.repo.checkAlreadyRunning",
    )

    check_job = create_running_maintenance_job(db, CheckJob, repo)

    schedule_background_job(check_v2_service.execute_check(check_job.id, repo.id))

    logger.info("Borg2 check job created", job_id=check_job.id, repository_id=repo.id,
                user=current_user.username)

    return {
        "job_id": check_job.id,
        "status": "running",
        "message": "backend.success.repo.checkJobStarted",
    }
