import secrets
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
import structlog

from app.core.agent_auth import AGENT_TOKEN_PREFIX_LENGTH, get_current_agent
from app.core.security import get_password_hash, verify_password
from app.database.database import get_db
from app.database.models import (
    AgentEnrollmentToken,
    AgentJob,
    AgentJobLog,
    AgentMachine,
    BackupJob,
    Repository,
)
from app.utils.datetime_utils import serialize_datetime

logger = structlog.get_logger()
router = APIRouter(prefix="/api/agents", tags=["agents"])

DEFAULT_AGENT_POLL_INTERVAL_SECONDS = 15


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _invalid_enrollment_token() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"key": "backend.errors.agents.invalidEnrollmentToken"},
    )


class AgentRegisterRequest(BaseModel):
    enrollment_token: str
    name: str
    hostname: Optional[str] = None
    os: Optional[str] = None
    arch: Optional[str] = None
    agent_version: Optional[str] = None
    borg_versions: list[dict[str, Any]] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)
    labels: dict[str, Any] = Field(default_factory=dict)


class AgentRegisterResponse(BaseModel):
    agent_id: str
    agent_token: str
    server_time: datetime
    poll_interval_seconds: int

    class Config:
        json_encoders = {datetime: lambda v: serialize_datetime(v)}


class AgentHeartbeatRequest(BaseModel):
    agent_id: str
    hostname: Optional[str] = None
    agent_version: Optional[str] = None
    borg_versions: list[dict[str, Any]] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)
    running_job_ids: list[int] = Field(default_factory=list)
    last_error: Optional[str] = None


class AgentHeartbeatResponse(BaseModel):
    server_time: datetime
    poll_interval_seconds: int
    cancel_job_ids: list[int]

    class Config:
        json_encoders = {datetime: lambda v: serialize_datetime(v)}


class AgentJobPollItem(BaseModel):
    id: int
    type: str
    status: str
    created_at: datetime
    payload: dict[str, Any]

    class Config:
        json_encoders = {datetime: lambda v: serialize_datetime(v)}


class AgentJobPollResponse(BaseModel):
    jobs: list[AgentJobPollItem]


class AgentJobStatusResponse(BaseModel):
    id: int
    status: str


class AgentJobStartRequest(BaseModel):
    started_at: Optional[datetime] = None


class AgentJobProgressRequest(BaseModel):
    progress_percent: Optional[float] = None
    current_file: Optional[str] = None
    original_size: Optional[int] = None
    compressed_size: Optional[int] = None
    deduplicated_size: Optional[int] = None
    nfiles: Optional[int] = None
    backup_speed: Optional[float] = None
    total_expected_size: Optional[int] = None
    estimated_time_remaining: Optional[int] = None


class AgentJobLogRequest(BaseModel):
    sequence: int = Field(ge=0)
    stream: str = "stdout"
    message: str
    created_at: Optional[datetime] = None


class AgentJobLogResponse(BaseModel):
    accepted: bool
    duplicate: bool = False


class AgentJobCompleteRequest(BaseModel):
    completed_at: Optional[datetime] = None
    result: dict[str, Any] = Field(default_factory=dict)


class AgentJobFailRequest(BaseModel):
    completed_at: Optional[datetime] = None
    error_message: str
    return_code: Optional[int] = None


class AgentJobCanceledRequest(BaseModel):
    completed_at: Optional[datetime] = None


def _resolve_enrollment_token(raw_token: str, db: Session) -> AgentEnrollmentToken:
    token_prefix = raw_token[:AGENT_TOKEN_PREFIX_LENGTH]
    candidates = (
        db.query(AgentEnrollmentToken)
        .filter(AgentEnrollmentToken.token_prefix == token_prefix)
        .all()
    )

    now = _now_utc()
    for token in candidates:
        if not verify_password(raw_token, token.token_hash):
            continue
        if token.revoked_at is not None or token.used_at is not None:
            raise _invalid_enrollment_token()
        if _as_utc(token.expires_at) <= now:
            raise _invalid_enrollment_token()
        return token

    raise _invalid_enrollment_token()


def _serialize_agent_job(job: AgentJob) -> AgentJobPollItem:
    return AgentJobPollItem(
        id=job.id,
        type=job.job_type,
        status=job.status,
        created_at=job.created_at,
        payload=job.payload or {},
    )


def _get_agent_job(job_id: int, current_agent: AgentMachine, db: Session) -> AgentJob:
    job = (
        db.query(AgentJob)
        .filter(
            AgentJob.id == job_id,
            AgentJob.agent_machine_id == current_agent.id,
        )
        .first()
    )
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"key": "backend.errors.agents.jobNotFound"},
        )
    return job


def _reject_final_job(job: AgentJob) -> None:
    if job.status in ("completed", "failed", "canceled"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"key": "backend.errors.agents.jobAlreadyFinished"},
        )


def _normalize_agent_timestamp(value: Optional[datetime]) -> datetime:
    if value is None:
        return _now_utc()
    return _as_utc(value)


def _get_linked_backup_job(job: AgentJob, db: Session) -> Optional[BackupJob]:
    if not job.backup_job_id:
        return None
    return db.query(BackupJob).filter(BackupJob.id == job.backup_job_id).first()


def _collect_agent_logs(job: AgentJob, db: Session) -> str:
    logs = (
        db.query(AgentJobLog)
        .filter(AgentJobLog.agent_job_id == job.id)
        .order_by(AgentJobLog.sequence.asc(), AgentJobLog.id.asc())
        .all()
    )
    return "\n".join(log.message for log in logs)


def _sync_backup_progress(agent_job: AgentJob, backup_job: BackupJob) -> None:
    for field_name in (
        "progress_percent",
        "current_file",
        "original_size",
        "compressed_size",
        "deduplicated_size",
        "nfiles",
        "backup_speed",
        "total_expected_size",
        "estimated_time_remaining",
    ):
        setattr(backup_job, field_name, getattr(agent_job, field_name))
    backup_job.progress = int(agent_job.progress_percent or 0)


def _finish_linked_backup_job(
    agent_job: AgentJob,
    db: Session,
    *,
    status_value: str,
    completed_at: datetime,
    error_message: Optional[str] = None,
) -> None:
    backup_job = _get_linked_backup_job(agent_job, db)
    if not backup_job:
        return

    backup_job.status = status_value
    backup_job.completed_at = completed_at
    backup_job.error_message = error_message
    backup_job.logs = _collect_agent_logs(agent_job, db)
    _sync_backup_progress(agent_job, backup_job)
    if status_value == "completed":
        backup_job.progress = 100
        backup_job.progress_percent = 100.0
        archive_name = (agent_job.result or {}).get("archive_name")
        if archive_name:
            backup_job.archive_name = archive_name

        repository = (
            db.query(Repository)
            .filter(Repository.path == backup_job.repository)
            .first()
        )
        if repository:
            repository.last_backup = completed_at
            repository.updated_at = _now_utc()


@router.post("/register", response_model=AgentRegisterResponse)
async def register_agent(
    payload: AgentRegisterRequest,
    db: Session = Depends(get_db),
):
    name = payload.name.strip()
    if not name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"key": "backend.errors.agents.agentNameRequired"},
        )

    enrollment_token = _resolve_enrollment_token(payload.enrollment_token, db)
    raw_agent_token = "borgui_agent_" + secrets.token_urlsafe(32)
    now = _now_utc()
    agent = AgentMachine(
        name=name,
        agent_id="agt_" + secrets.token_urlsafe(16),
        token_hash=get_password_hash(raw_agent_token),
        token_prefix=raw_agent_token[:AGENT_TOKEN_PREFIX_LENGTH],
        hostname=payload.hostname,
        os=payload.os,
        arch=payload.arch,
        agent_version=payload.agent_version,
        borg_versions=payload.borg_versions,
        capabilities=payload.capabilities,
        labels=payload.labels,
        status="online",
        last_seen_at=now,
        created_at=now,
        updated_at=now,
    )
    db.add(agent)
    db.flush()

    enrollment_token.used_at = now
    enrollment_token.used_by_agent_id = agent.id
    db.commit()
    db.refresh(agent)

    logger.info(
        "Agent registered",
        agent_id=agent.agent_id,
        agent_name=agent.name,
        enrollment_token_id=enrollment_token.id,
    )

    return AgentRegisterResponse(
        agent_id=agent.agent_id,
        agent_token=raw_agent_token,
        server_time=now,
        poll_interval_seconds=DEFAULT_AGENT_POLL_INTERVAL_SECONDS,
    )


@router.post("/heartbeat", response_model=AgentHeartbeatResponse)
async def heartbeat(
    payload: AgentHeartbeatRequest,
    current_agent: AgentMachine = Depends(get_current_agent),
    db: Session = Depends(get_db),
):
    if payload.agent_id != current_agent.agent_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"key": "backend.errors.agents.agentIdMismatch"},
        )

    now = _now_utc()
    current_agent.hostname = payload.hostname or current_agent.hostname
    current_agent.agent_version = payload.agent_version or current_agent.agent_version
    current_agent.borg_versions = payload.borg_versions
    current_agent.capabilities = payload.capabilities
    current_agent.last_error = payload.last_error
    current_agent.status = "online"
    current_agent.last_seen_at = now
    current_agent.updated_at = now
    db.commit()

    cancel_job_ids = (
        db.query(AgentJob.id)
        .filter(
            AgentJob.agent_machine_id == current_agent.id,
            AgentJob.status == "cancel_requested",
            AgentJob.id.in_(payload.running_job_ids or [0]),
        )
        .all()
    )

    return AgentHeartbeatResponse(
        server_time=now,
        poll_interval_seconds=DEFAULT_AGENT_POLL_INTERVAL_SECONDS,
        cancel_job_ids=[row[0] for row in cancel_job_ids],
    )


@router.post("/unregister", status_code=status.HTTP_204_NO_CONTENT)
async def unregister_agent(
    current_agent: AgentMachine = Depends(get_current_agent),
    db: Session = Depends(get_db),
):
    if current_agent.status != "revoked":
        current_agent.status = "revoked"
        current_agent.updated_at = _now_utc()
        db.commit()
        logger.info(
            "Agent unregistered",
            agent_id=current_agent.agent_id,
            agent_name=current_agent.name,
        )


@router.get("/jobs/poll", response_model=AgentJobPollResponse)
async def poll_jobs(
    limit: int = Query(default=1, ge=1, le=10),
    current_agent: AgentMachine = Depends(get_current_agent),
    db: Session = Depends(get_db),
):
    jobs = (
        db.query(AgentJob)
        .filter(
            AgentJob.agent_machine_id == current_agent.id,
            AgentJob.status == "queued",
        )
        .order_by(AgentJob.created_at.asc(), AgentJob.id.asc())
        .limit(limit)
        .all()
    )
    return AgentJobPollResponse(jobs=[_serialize_agent_job(job) for job in jobs])


@router.post("/jobs/{job_id}/claim", response_model=AgentJobStatusResponse)
async def claim_job(
    job_id: int,
    current_agent: AgentMachine = Depends(get_current_agent),
    db: Session = Depends(get_db),
):
    job = _get_agent_job(job_id, current_agent, db)
    _reject_final_job(job)

    if job.status == "queued":
        now = _now_utc()
        job.status = "claimed"
        job.claimed_at = now
        job.updated_at = now
        db.commit()

    return AgentJobStatusResponse(id=job.id, status=job.status)


@router.post("/jobs/{job_id}/start", response_model=AgentJobStatusResponse)
async def start_job(
    job_id: int,
    payload: AgentJobStartRequest,
    current_agent: AgentMachine = Depends(get_current_agent),
    db: Session = Depends(get_db),
):
    job = _get_agent_job(job_id, current_agent, db)
    _reject_final_job(job)

    if job.status not in ("queued", "claimed", "cancel_requested", "running"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"key": "backend.errors.agents.jobNotStartable"},
        )

    now = _now_utc()
    if job.claimed_at is None:
        job.claimed_at = now
    if job.started_at is None:
        job.started_at = _normalize_agent_timestamp(payload.started_at)
    if job.status != "cancel_requested":
        job.status = "running"
    backup_job = _get_linked_backup_job(job, db)
    if backup_job:
        backup_job.status = "running"
        if backup_job.started_at is None:
            backup_job.started_at = job.started_at
    job.updated_at = now
    db.commit()

    return AgentJobStatusResponse(id=job.id, status=job.status)


@router.post("/jobs/{job_id}/progress", response_model=AgentJobStatusResponse)
async def update_job_progress(
    job_id: int,
    payload: AgentJobProgressRequest,
    current_agent: AgentMachine = Depends(get_current_agent),
    db: Session = Depends(get_db),
):
    job = _get_agent_job(job_id, current_agent, db)
    _reject_final_job(job)

    progress = payload.model_dump(exclude_none=True)
    for field_name, value in progress.items():
        setattr(job, field_name, value)
    job.progress = progress
    backup_job = _get_linked_backup_job(job, db)
    if backup_job:
        backup_job.status = "running"
        _sync_backup_progress(job, backup_job)
    job.updated_at = _now_utc()
    db.commit()

    return AgentJobStatusResponse(id=job.id, status=job.status)


@router.post("/jobs/{job_id}/logs", response_model=AgentJobLogResponse)
async def upload_job_log(
    job_id: int,
    payload: AgentJobLogRequest,
    current_agent: AgentMachine = Depends(get_current_agent),
    db: Session = Depends(get_db),
):
    job = _get_agent_job(job_id, current_agent, db)
    existing_log = (
        db.query(AgentJobLog)
        .filter(
            AgentJobLog.agent_job_id == job.id,
            AgentJobLog.sequence == payload.sequence,
        )
        .first()
    )
    if existing_log:
        return AgentJobLogResponse(accepted=True, duplicate=True)

    db.add(
        AgentJobLog(
            agent_job_id=job.id,
            sequence=payload.sequence,
            stream=payload.stream,
            message=payload.message,
            created_at=_normalize_agent_timestamp(payload.created_at),
            received_at=_now_utc(),
        )
    )
    job.updated_at = _now_utc()
    db.commit()

    return AgentJobLogResponse(accepted=True, duplicate=False)


@router.post("/jobs/{job_id}/complete", response_model=AgentJobStatusResponse)
async def complete_job(
    job_id: int,
    payload: AgentJobCompleteRequest,
    current_agent: AgentMachine = Depends(get_current_agent),
    db: Session = Depends(get_db),
):
    job = _get_agent_job(job_id, current_agent, db)
    _reject_final_job(job)

    now = _now_utc()
    job.status = "completed"
    job.completed_at = _normalize_agent_timestamp(payload.completed_at)
    job.result = payload.result
    job.error_message = None
    job.updated_at = now
    _finish_linked_backup_job(
        job,
        db,
        status_value="completed",
        completed_at=job.completed_at,
    )
    db.commit()

    return AgentJobStatusResponse(id=job.id, status=job.status)


@router.post("/jobs/{job_id}/fail", response_model=AgentJobStatusResponse)
async def fail_job(
    job_id: int,
    payload: AgentJobFailRequest,
    current_agent: AgentMachine = Depends(get_current_agent),
    db: Session = Depends(get_db),
):
    job = _get_agent_job(job_id, current_agent, db)
    _reject_final_job(job)

    result = {}
    if payload.return_code is not None:
        result["return_code"] = payload.return_code

    now = _now_utc()
    job.status = "failed"
    job.completed_at = _normalize_agent_timestamp(payload.completed_at)
    job.error_message = payload.error_message
    job.result = result
    job.updated_at = now
    _finish_linked_backup_job(
        job,
        db,
        status_value="failed",
        completed_at=job.completed_at,
        error_message=payload.error_message,
    )
    db.commit()

    return AgentJobStatusResponse(id=job.id, status=job.status)


@router.post("/jobs/{job_id}/cancel", response_model=AgentJobStatusResponse)
async def mark_job_canceled(
    job_id: int,
    payload: AgentJobCanceledRequest,
    current_agent: AgentMachine = Depends(get_current_agent),
    db: Session = Depends(get_db),
):
    job = _get_agent_job(job_id, current_agent, db)
    _reject_final_job(job)

    now = _now_utc()
    job.status = "canceled"
    job.completed_at = _normalize_agent_timestamp(payload.completed_at)
    job.updated_at = now
    _finish_linked_backup_job(
        job,
        db,
        status_value="cancelled",
        completed_at=job.completed_at,
        error_message="Agent job canceled",
    )
    db.commit()

    return AgentJobStatusResponse(id=job.id, status=job.status)
