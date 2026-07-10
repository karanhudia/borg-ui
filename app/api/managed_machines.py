import ipaddress
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
import structlog

from app.core.agent_auth import AGENT_TOKEN_PREFIX_LENGTH
from app.core.agent_constants import AGENT_FILESYSTEM_BROWSE_TIMEOUT_SECONDS
from app.core.features import require_feature_access
from app.core.security import get_current_admin_user, get_password_hash
from app.database.database import get_db
from app.database.models import (
    AgentEnrollmentToken,
    AgentJob,
    AgentJobLog,
    AgentMachine,
    User,
)
from app.services.agent_job_dispatcher import (
    dispatch_agent_cancel_if_connected,
    dispatch_agent_job_best_effort,
)
from app.services.agent_filesystem_service import browse_agent_filesystem
from app.services.agent_connection_manager import agent_connection_manager
from app.services.agent_connection_manager import (
    AgentCommandError,
    AgentCommandTimeout,
    AgentConnectionUnavailable,
)
from app.services.log_policy import get_log_save_policy, job_has_logs_by_policy
from app.utils.datetime_utils import serialize_datetime

logger = structlog.get_logger()
router = APIRouter(prefix="/api/managed-machines", tags=["managed-machines"])

AGENT_DIAGNOSTICS_TIMEOUT_SECONDS = 5.0
_DIAGNOSTIC_HOST_RE = re.compile(
    r"^(?=.{1,253}\.?$)"
    r"(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)*"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.?$"
)


def require_managed_agents_admin_user(
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
) -> User:
    require_feature_access(db, "managed_agents")
    return current_user


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


class AgentEnrollmentTokenCreate(BaseModel):
    name: str
    default_path: Optional[str] = None
    expires_in_minutes: Optional[int] = Field(default=None, ge=1, le=60 * 24 * 30)
    expires_in_hours: Optional[int] = Field(default=None, ge=1, le=24 * 30)
    expires_in_days: Optional[int] = Field(default=None, ge=1, le=30)
    expires_never: bool = False


class AgentEnrollmentTokenCreated(BaseModel):
    id: int
    name: str
    token: str
    token_prefix: str
    default_path: Optional[str] = None
    expires_at: Optional[datetime]
    created_at: datetime

    class Config:
        json_encoders = {datetime: lambda v: serialize_datetime(v)}


class AgentEnrollmentTokenSummary(BaseModel):
    id: int
    name: str
    token_prefix: str
    default_path: Optional[str] = None
    expires_at: Optional[datetime]
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
    default_path: Optional[str] = None
    borg_versions: Optional[list[dict[str, Any]]] = None
    capabilities: Optional[list[str]] = None
    labels: Optional[dict[str, Any]] = None
    status: str
    last_seen_at: Optional[datetime] = None
    last_error: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime] = None

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


class AgentSessionLogEntryResponse(BaseModel):
    id: str
    agent_machine_id: int
    job_id: Optional[int] = None
    command_id: Optional[str] = None
    stream: str
    level: str
    message: str
    created_at: str


class AgentDiagnosticTarget(BaseModel):
    host: str
    port: int = Field(ge=1, le=65535)
    timeout_seconds: float = Field(default=3.0, ge=0.5, le=10.0)


class AgentDiagnosticsRequest(BaseModel):
    target: Optional[AgentDiagnosticTarget] = None


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


def _optional_trimmed(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _validate_diagnostic_host(host: str) -> str:
    stripped = host.strip()
    if not stripped:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"key": "backend.errors.agents.diagnosticsTargetHostRequired"},
        )

    try:
        ipaddress.ip_address(stripped)
        return stripped
    except ValueError:
        pass

    if not _DIAGNOSTIC_HOST_RE.fullmatch(stripped):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"key": "backend.errors.agents.diagnosticsTargetHostInvalid"},
        )
    return stripped


def _diagnostic_agent_metadata(agent: AgentMachine) -> dict[str, Any]:
    return {
        "id": agent.id,
        "name": agent.name,
        "agent_id": agent.agent_id,
        "hostname": agent.hostname,
        "status": agent.status,
        "last_seen_at": (
            serialize_datetime(agent.last_seen_at) if agent.last_seen_at else None
        ),
        "agent_version": agent.agent_version,
        "borg_versions": agent.borg_versions or [],
        "capabilities": agent.capabilities or [],
        "last_error": agent.last_error,
    }


def _diagnostics_error_response(
    agent: AgentMachine,
    *,
    session_status: str,
    error: str,
    message: str,
) -> dict[str, Any]:
    return {
        "agent": _diagnostic_agent_metadata(agent),
        "session": {
            "status": session_status,
            "elapsed_ms": None,
            "error": error,
            "message": message,
        },
        "tcp": None,
    }


def _normalize_diagnostics_result(
    agent: AgentMachine,
    result: dict[str, Any],
) -> dict[str, Any]:
    session_result = (
        result.get("session") if isinstance(result.get("session"), dict) else {}
    )
    normalized: dict[str, Any] = {
        "agent": _diagnostic_agent_metadata(agent),
        "session": {
            "status": str(session_result.get("status") or "success"),
        },
        "tcp": None,
    }
    if "elapsed_ms" in session_result:
        normalized["session"]["elapsed_ms"] = session_result.get("elapsed_ms")
    for key in ("error", "message"):
        if session_result.get(key):
            normalized["session"][key] = session_result[key]

    tcp_result = result.get("tcp")
    if isinstance(tcp_result, dict):
        normalized["tcp"] = tcp_result
    return normalized


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


def _enrollment_expires_at(
    payload: AgentEnrollmentTokenCreate, now: datetime
) -> Optional[datetime]:
    provided_expiry_fields = [
        payload.expires_in_minutes is not None,
        payload.expires_in_hours is not None,
        payload.expires_in_days is not None,
        payload.expires_never,
    ]
    if sum(1 for is_provided in provided_expiry_fields if is_provided) > 1:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"key": "backend.errors.agents.enrollmentExpiryAmbiguous"},
        )

    if payload.expires_never:
        return None

    minutes = payload.expires_in_minutes
    if payload.expires_in_hours is not None:
        minutes = payload.expires_in_hours * 60
    if payload.expires_in_days is not None:
        minutes = payload.expires_in_days * 24 * 60
    if minutes is None:
        minutes = 60

    if minutes < 5:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"key": "backend.errors.agents.enrollmentExpiryTooShort"},
        )

    return now + timedelta(minutes=minutes)


@router.post(
    "/enrollment-tokens",
    response_model=AgentEnrollmentTokenCreated,
    status_code=status.HTTP_201_CREATED,
)
async def create_enrollment_token(
    payload: AgentEnrollmentTokenCreate,
    current_user: User = Depends(require_managed_agents_admin_user),
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
        default_path=_optional_trimmed(payload.default_path),
        created_by_user_id=current_user.id,
        expires_at=_enrollment_expires_at(payload, now),
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
        default_path=token.default_path,
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
    current_user: User = Depends(require_managed_agents_admin_user),
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
    agents = (
        db.query(AgentMachine)
        .filter(AgentMachine.status != "deleted")
        .order_by(AgentMachine.name.asc())
        .all()
    )
    now = _now_utc()
    changed = False
    for agent in agents:
        if agent.status == "offline" and agent_connection_manager.is_connected(
            agent.id
        ):
            agent.status = "online"
            agent.last_seen_at = now
            agent.updated_at = now
            changed = True
    if changed:
        db.commit()
    return agents


@router.post(
    "/agents/{agent_machine_id}/backup-jobs",
    response_model=AgentJobResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_agent_backup_job(
    agent_machine_id: int,
    payload: AgentBackupJobCreate,
    current_user: User = Depends(require_managed_agents_admin_user),
    db: Session = Depends(get_db),
):
    agent = db.query(AgentMachine).filter(AgentMachine.id == agent_machine_id).first()
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"key": "backend.errors.agents.agentNotFound"},
        )
    if agent.status in ("disabled", "revoked", "deleted"):
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
    await dispatch_agent_job_best_effort(db, job, source="backup_job_create")

    logger.info(
        "Agent backup job queued",
        user=current_user.username,
        agent_id=agent.agent_id,
        job_id=job.id,
    )
    return job


@router.get("/agents/{agent_machine_id}/filesystem/browse")
async def browse_agent_machine_filesystem(
    agent_machine_id: int,
    path: str = "/",
    include_hidden: bool = False,
    _: User = Depends(require_managed_agents_admin_user),
    db: Session = Depends(get_db),
):
    return await browse_agent_filesystem(
        db,
        agent_machine_id,
        path=path,
        include_hidden=include_hidden,
        timeout_seconds=AGENT_FILESYSTEM_BROWSE_TIMEOUT_SECONDS,
    )


@router.get("/agents/{agent_machine_id}/repository-defaults")
async def get_agent_machine_repository_defaults(
    agent_machine_id: int,
    _: User = Depends(require_managed_agents_admin_user),
    db: Session = Depends(get_db),
):
    """Ask a connected managed agent for its environment-configured repository
    target (``$BORG_REPO`` / ``$BORG_REMOTE_PATH``) so the repository wizard can
    pre-fill the form. Returns nulls when the agent is offline or does not set
    them; no secrets are requested."""
    agent = (
        db.query(AgentMachine)
        .filter(
            AgentMachine.id == agent_machine_id,
            AgentMachine.status != "deleted",
        )
        .first()
    )
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"key": "backend.errors.agents.agentNotFound"},
        )
    try:
        result = await agent_connection_manager.send_command(
            agent.id,
            command="agent.repository_defaults",
            payload={},
            timeout_seconds=AGENT_FILESYSTEM_BROWSE_TIMEOUT_SECONDS,
            wait_for_result=True,
        )
    except (AgentConnectionUnavailable, AgentCommandTimeout, AgentCommandError):
        return {"repo": None, "remote_path": None, "has_passphrase": False}
    if not isinstance(result, dict):
        return {"repo": None, "remote_path": None, "has_passphrase": False}
    return {
        "repo": result.get("repo"),
        "remote_path": result.get("remote_path"),
        "has_passphrase": bool(result.get("has_passphrase")),
    }


@router.post("/agents/{agent_machine_id}/diagnostics")
async def run_agent_machine_diagnostics(
    agent_machine_id: int,
    payload: AgentDiagnosticsRequest,
    _: User = Depends(require_managed_agents_admin_user),
    db: Session = Depends(get_db),
):
    agent = db.query(AgentMachine).filter(AgentMachine.id == agent_machine_id).first()
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"key": "backend.errors.agents.agentNotFound"},
        )

    command_payload: dict[str, Any] = {}
    if payload.target is not None:
        command_payload["target"] = {
            "host": _validate_diagnostic_host(payload.target.host),
            "port": payload.target.port,
            "timeout_seconds": float(payload.target.timeout_seconds),
        }

    try:
        result = await agent_connection_manager.send_command(
            agent.id,
            command="diagnostics.run",
            payload=command_payload,
            timeout_seconds=AGENT_DIAGNOSTICS_TIMEOUT_SECONDS,
            wait_for_result=True,
        )
    except AgentConnectionUnavailable as exc:
        return _diagnostics_error_response(
            agent,
            session_status="offline",
            error="agent_offline",
            message=str(exc),
        )
    except AgentCommandTimeout:
        return _diagnostics_error_response(
            agent,
            session_status="timeout",
            error="agent_timeout",
            message="Agent did not return diagnostics before the timeout",
        )
    except AgentCommandError as exc:
        return _diagnostics_error_response(
            agent,
            session_status="failed",
            error=str(exc.payload.get("code") or "agent_command_failed"),
            message=str(exc),
        )

    return _normalize_diagnostics_result(agent, result)


@router.get(
    "/agents/{agent_machine_id}/logs",
    response_model=list[AgentSessionLogEntryResponse],
)
async def list_agent_machine_logs(
    agent_machine_id: int,
    _: User = Depends(require_managed_agents_admin_user),
    db: Session = Depends(get_db),
):
    agent = db.query(AgentMachine).filter(AgentMachine.id == agent_machine_id).first()
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"key": "backend.errors.agents.agentNotFound"},
        )
    return agent_connection_manager.list_logs(agent.id)


@router.post(
    "/agents/{agent_machine_id}/revoke", status_code=status.HTTP_204_NO_CONTENT
)
async def revoke_agent_machine(
    agent_machine_id: int,
    current_user: User = Depends(require_managed_agents_admin_user),
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


@router.delete("/agents/{agent_machine_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent_machine(
    agent_machine_id: int,
    current_user: User = Depends(require_managed_agents_admin_user),
    db: Session = Depends(get_db),
):
    agent = db.query(AgentMachine).filter(AgentMachine.id == agent_machine_id).first()
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"key": "backend.errors.agents.agentNotFound"},
        )

    if agent.status != "deleted":
        now = _now_utc()
        agent.status = "deleted"
        agent.deleted_at = now
        agent.updated_at = now
        db.commit()
        logger.info(
            "Agent machine deleted",
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
    _: User = Depends(require_managed_agents_admin_user),
    db: Session = Depends(get_db),
):
    job = db.query(AgentJob).filter(AgentJob.id == job_id).first()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"key": "backend.errors.agents.jobNotFound"},
        )

    logs = (
        db.query(AgentJobLog)
        .filter(AgentJobLog.agent_job_id == job.id)
        .order_by(AgentJobLog.sequence.asc(), AgentJobLog.id.asc())
        .all()
    )
    if not job_has_logs_by_policy(
        job,
        get_log_save_policy(db),
        output_text=[*(log.message for log in logs), job.error_message],
    ):
        return []

    return logs


@router.post(
    "/agent-jobs/{job_id}/cancel",
    response_model=AgentJobResponse,
)
async def request_agent_job_cancel(
    job_id: int,
    current_user: User = Depends(require_managed_agents_admin_user),
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
    await dispatch_agent_cancel_if_connected(job)
    logger.info(
        "Agent job cancellation requested",
        user=current_user.username,
        job_id=job.id,
    )
    return job
