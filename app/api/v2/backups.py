"""Borg 2 backup operation endpoints — mounted at /api/v2/backup/

Handles create, prune, compact, and check for Borg 2 repositories.
Compact is a first-class operation in Borg 2 (not optional — space is never
freed automatically after delete or prune).
"""

import json
import asyncio
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional
import structlog

from app.database.database import get_db, SessionLocal
from app.database.models import User, Repository, CheckJob, CompactJob
from app.core.security import get_current_user
from app.core.features import require_feature
from app.core.borg2 import borg2
from app.services.v2.check_service import check_v2_service
from app.services.v2.compact_service import compact_v2_service

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

def _get_v2_repo_by_id(repo_id: int, db: Session) -> Repository:
    repo = db.query(Repository).filter(
        Repository.id == repo_id, Repository.borg_version == 2
    ).first()
    if not repo:
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
    repo = _get_v2_repo_by_id(data.repository_id, db)
    source_dirs = _source_dirs(repo)
    if not source_dirs:
        raise HTTPException(
            status_code=400,
            detail={"key": "backend.errors.backup.noSourceDirectories"},
        )

    result = await borg2.create(
        repository=repo.path,
        source_paths=source_dirs,
        compression=repo.compression or "lz4",
        archive_name=data.archive_name,
        passphrase=repo.passphrase,
        remote_path=repo.remote_path,
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

    repo = _get_v2_repo_by_id(data.repository_id, db)
    result = await borg2.prune_archives(
        repository=repo.path,
        keep_hourly=data.keep_hourly,
        keep_daily=data.keep_daily,
        keep_weekly=data.keep_weekly,
        keep_monthly=data.keep_monthly,
        keep_quarterly=data.keep_quarterly,
        keep_yearly=data.keep_yearly,
        dry_run=data.dry_run,
        passphrase=repo.passphrase,
        remote_path=repo.remote_path,
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

    repo = _get_v2_repo_by_id(data.repository_id, db)

    running = db.query(CompactJob).filter(
        CompactJob.repository_id == repo.id,
        CompactJob.status == "running",
    ).first()
    if running:
        raise HTTPException(
            status_code=409,
            detail={"key": "backend.errors.compact.alreadyRunning"},
        )

    compact_job = CompactJob(
        repository_id=repo.id,
        repository_path=repo.path,
        status="running",
        started_at=datetime.utcnow(),
        progress=0,
    )
    db.add(compact_job)
    db.commit()
    db.refresh(compact_job)

    asyncio.create_task(
        compact_v2_service.execute_compact(compact_job.id, repo.id)
    )

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

    repo = _get_v2_repo_by_id(data.repository_id, db)

    # Reject if a check is already running for this repository
    running = db.query(CheckJob).filter(
        CheckJob.repository_id == repo.id,
        CheckJob.status == "running",
    ).first()
    if running:
        raise HTTPException(
            status_code=409,
            detail={"key": "backend.errors.repo.checkAlreadyRunning"},
        )

    check_job = CheckJob(
        repository_id=repo.id,
        repository_path=repo.path,
        status="running",
        started_at=datetime.utcnow(),
        progress=0,
    )
    db.add(check_job)
    db.commit()
    db.refresh(check_job)

    asyncio.create_task(
        check_v2_service.execute_check(check_job.id, repo.id)
    )

    logger.info("Borg2 check job created", job_id=check_job.id, repository_id=repo.id,
                user=current_user.username)

    return {
        "job_id": check_job.id,
        "status": "running",
        "message": "backend.success.repo.checkJobStarted",
    }
