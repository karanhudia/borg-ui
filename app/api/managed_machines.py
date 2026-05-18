import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
import structlog

from app.core.agent_auth import AGENT_TOKEN_PREFIX_LENGTH
from app.core.security import get_current_admin_user, get_password_hash
from app.database.database import get_db
from app.database.models import (
    AgentEnrollmentToken,
    AgentJob,
    AgentJobLog,
    AgentMachine,
    User,
)
from app.utils.datetime_utils import serialize_datetime

logger = structlog.get_logger()
router = APIRouter(prefix="/api/managed-machines", tags=["managed-machines"])


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


class AgentEnrollmentTokenCreate(BaseModel):
    name: str
    expires_in_minutes: int = Field(default=60, ge=1, le=60 * 24 * 30)


class AgentEnrollmentTokenCreated(BaseModel):
    id: int
    name: str
    token: str
    token_prefix: str
    expires_at: datetime
    created_at: datetime

    class Config:
        json_encoders = {datetime: lambda v: serialize_datetime(v)}


class AgentEnrollmentTokenSummary(BaseModel):
    id: int
    name: str
    token_prefix: str
    expires_at: datetime
    used_at: Optional[datetime] = None
    used_by_agent_id: Optional[int] = None
    revoked_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True
        json_encoders = {datetime: lambda v: serialize_datetime(v)}


class AgentMachineResponse(BaseModel):
    id: int
    name: str
    agent_id: str
    hostname: Optional[str] = None
    os: Optional[str] = None
    arch: Optional[str] = None
    agent_version: Optional[str] = None
    borg_versions: Optional[list[dict[str, Any]]] = None
    capabilities: Optional[list[str]] = None
    labels: Optional[dict[str, Any]] = None
    status: str
    last_seen_at: Optional[datetime] = None
    last_error: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
        json_encoders = {datetime: lambda v: serialize_datetime(v)}


class AgentJobResponse(BaseModel):
    id: int
    agent_machine_id: int
    backup_job_id: Optional[int] = None
    job_type: str
    status: str
    payload: dict[str, Any]
    result: Optional[dict[str, Any]] = None
    claimed_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    progress_percent: Optional[float] = None
    current_file: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
        json_encoders = {datetime: lambda v: serialize_datetime(v)}


class AgentJobLogEntryResponse(BaseModel):
    id: int
    agent_job_id: int
    sequence: int
    stream: str
    message: str
    created_at: datetime
    received_at: datetime

    class Config:
        from_attributes = True
        json_encoders = {datetime: lambda v: serialize_datetime(v)}


class AgentBackupJobCreate(BaseModel):
    repository_path: str
    archive_name: str
    source_paths: list[str] = Field(min_length=1)
    borg_version: int = Field(default=1, ge=1, le=2)
    borg_binary: Optional[str] = None
    compression: str = "lz4"
    exclude_patterns: list[str] = Field(default_factory=list)
    custom_flags: list[str] = Field(default_factory=list)
    remote_path: Optional[str] = None
    repository_id: Optional[int] = None
    secrets: dict[str, Any] = Field(default_factory=dict)


def _require_nonempty_string(value: str, error_key: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"key": error_key},
        )
    return stripped


def _build_backup_job_payload(payload: AgentBackupJobCreate) -> dict[str, Any]:
    source_paths = [
        _require_nonempty_string(path, "backend.errors.agents.backupSourcePathRequired")
        for path in payload.source_paths
    ]
    repository: dict[str, Any] = {
        "path": _require_nonempty_string(
            payload.repository_path,
            "backend.errors.agents.backupRepositoryPathRequired",
        ),
        "borg_version": payload.borg_version,
    }
    if payload.repository_id is not None:
        repository["id"] = payload.repository_id
    if payload.borg_binary:
        repository["borg_binary"] = payload.borg_binary.strip()
    if payload.remote_path:
        repository["remote_path"] = payload.remote_path.strip()

    return {
        "schema_version": 1,
        "job_kind": "backup.create",
        "repository": repository,
        "backup": {
            "archive_name": _require_nonempty_string(
                payload.archive_name,
                "backend.errors.agents.backupArchiveNameRequired",
            ),
            "source_paths": source_paths,
            "compression": payload.compression.strip() or "lz4",
            "exclude_patterns": payload.exclude_patterns,
            "custom_flags": payload.custom_flags,
        },
        "secrets": payload.secrets,
    }


@router.post(
    "/enrollment-tokens",
    response_model=AgentEnrollmentTokenCreated,
    status_code=status.HTTP_201_CREATED,
)
async def create_enrollment_token(
    payload: AgentEnrollmentTokenCreate,
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    name = payload.name.strip()
    if not name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"key": "backend.errors.agents.enrollmentNameRequired"},
        )

    raw_token = "borgui_enroll_" + secrets.token_urlsafe(32)
    now = _now_utc()
    token = AgentEnrollmentToken(
        name=name,
        token_hash=get_password_hash(raw_token),
        token_prefix=raw_token[:AGENT_TOKEN_PREFIX_LENGTH],
        created_by_user_id=current_user.id,
        expires_at=now + timedelta(minutes=payload.expires_in_minutes),
        created_at=now,
    )
    db.add(token)
    db.commit()
    db.refresh(token)

    logger.info(
        "Agent enrollment token created",
        user=current_user.username,
        token_id=token.id,
        token_name=token.name,
    )

    return AgentEnrollmentTokenCreated(
        id=token.id,
        name=token.name,
        token=raw_token,
        token_prefix=token.token_prefix,
        expires_at=token.expires_at,
        created_at=token.created_at,
    )


@router.get("/enrollment-tokens", response_model=list[AgentEnrollmentTokenSummary])
async def list_enrollment_tokens(
    _: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    return (
        db.query(AgentEnrollmentToken)
        .order_by(AgentEnrollmentToken.created_at.desc())
        .all()
    )


@router.post(
    "/enrollment-tokens/{token_id}/revoke", status_code=status.HTTP_204_NO_CONTENT
)
async def revoke_enrollment_token(
    token_id: int,
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    token = (
        db.query(AgentEnrollmentToken)
        .filter(AgentEnrollmentToken.id == token_id)
        .first()
    )
    if not token:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"key": "backend.errors.agents.enrollmentTokenNotFound"},
        )

    if token.revoked_at is None:
        token.revoked_at = _now_utc()
        db.commit()
        logger.info(
            "Agent enrollment token revoked",
            user=current_user.username,
            token_id=token.id,
        )


@router.get("/agents", response_model=list[AgentMachineResponse])
async def list_agent_machines(
    _: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    return db.query(AgentMachine).order_by(AgentMachine.name.asc()).all()


@router.post(
    "/agents/{agent_machine_id}/backup-jobs",
    response_model=AgentJobResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_agent_backup_job(
    agent_machine_id: int,
    payload: AgentBackupJobCreate,
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    agent = db.query(AgentMachine).filter(AgentMachine.id == agent_machine_id).first()
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

    now = _now_utc()
    job = AgentJob(
        agent_machine_id=agent.id,
        job_type="backup",
        status="queued",
        payload=_build_backup_job_payload(payload),
        created_at=now,
        updated_at=now,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    logger.info(
        "Agent backup job queued",
        user=current_user.username,
        agent_id=agent.agent_id,
        job_id=job.id,
    )
    return job


@router.post(
    "/agents/{agent_machine_id}/revoke", status_code=status.HTTP_204_NO_CONTENT
)
async def revoke_agent_machine(
    agent_machine_id: int,
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    agent = db.query(AgentMachine).filter(AgentMachine.id == agent_machine_id).first()
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"key": "backend.errors.agents.agentNotFound"},
        )

    if agent.status != "revoked":
        agent.status = "revoked"
        agent.updated_at = _now_utc()
        db.commit()
        logger.info(
            "Agent machine revoked",
            user=current_user.username,
            agent_id=agent.agent_id,
        )


@router.get("/agent-jobs", response_model=list[AgentJobResponse])
async def list_agent_jobs(
    _: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    return db.query(AgentJob).order_by(AgentJob.created_at.desc()).all()


@router.get(
    "/agent-jobs/{job_id}/logs",
    response_model=list[AgentJobLogEntryResponse],
)
async def list_agent_job_logs(
    job_id: int,
    _: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    job = db.query(AgentJob).filter(AgentJob.id == job_id).first()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"key": "backend.errors.agents.jobNotFound"},
        )

    return (
        db.query(AgentJobLog)
        .filter(AgentJobLog.agent_job_id == job.id)
        .order_by(AgentJobLog.sequence.asc(), AgentJobLog.id.asc())
        .all()
    )


@router.post(
    "/agent-jobs/{job_id}/cancel",
    response_model=AgentJobResponse,
)
async def request_agent_job_cancel(
    job_id: int,
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    job = db.query(AgentJob).filter(AgentJob.id == job_id).first()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"key": "backend.errors.agents.jobNotFound"},
        )
    if job.status in ("completed", "failed", "canceled"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"key": "backend.errors.agents.jobAlreadyFinished"},
        )

    job.status = "cancel_requested"
    job.updated_at = _now_utc()
    db.commit()
    db.refresh(job)
    logger.info(
        "Agent job cancellation requested",
        user=current_user.username,
        job_id=job.id,
    )
    return job
