import asyncio
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Request,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
import structlog

from app.core.agent_auth import (
    AGENT_AUTH_HEADER,
    AGENT_TOKEN_PREFIX_LENGTH,
    get_current_agent,
    resolve_agent_from_token,
)
from app.core.agent_constants import DEFAULT_AGENT_POLL_INTERVAL_SECONDS
from app.core.security import get_password_hash, verify_password
from app.database.database import get_db
from app.database.models import (
    AgentEnrollmentToken,
    AgentJob,
    AgentJobLog,
    AgentMachine,
    BackupJob,
    CheckJob,
    CompactJob,
    PruneJob,
    Repository,
)
from app.services.agent_artifact_relay import agent_artifact_relay
from app.services.agent_connection_manager import (
    AgentConnection,
    agent_connection_manager,
)
from app.services.agent_job_dispatcher import (
    agent_job_kind as live_agent_job_kind,
    dispatch_agent_job_best_effort,
)
from app.utils.datetime_utils import serialize_datetime

logger = structlog.get_logger()
router = APIRouter(prefix="/api/agents", tags=["agents"])
AGENT_SESSION_HELLO_TIMEOUT_SECONDS = 10.0

FINAL_AGENT_JOB_STATUSES = {"completed", "failed", "canceled"}
STALE_AGENT_JOB_REQUEUE_AFTER = timedelta(minutes=15)
REPOSITORY_OPERATION_JOB_MODELS = {
    "check": CheckJob,
    "compact": CompactJob,
    "prune": PruneJob,
}


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


class AgentSessionHello(BaseModel):
    type: str
    agent_id: str
    hostname: Optional[str] = None
    agent_version: Optional[str] = None
    borg_versions: list[dict[str, Any]] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)
    running_job_ids: list[int] = Field(default_factory=list)


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
        if token.expires_at is not None and _as_utc(token.expires_at) <= now:
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
    if job.status in FINAL_AGENT_JOB_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"key": "backend.errors.agents.jobAlreadyFinished"},
        )


def _job_activity_at(job: AgentJob) -> datetime:
    for value in (job.updated_at, job.started_at, job.claimed_at, job.created_at):
        if value is not None:
            return _as_utc(value)
    return _now_utc()


def _is_terminal_backup_status(status_value: Optional[str]) -> bool:
    return status_value in {
        "completed",
        "completed_with_warnings",
        "failed",
        "cancelled",
    }


# Repository ops that exist only to serve a synchronous, read-only UI request
# (browse/info) or a one-shot repo init. They have no durable record, so once the
# HTTP request that queued them times out there is no receiver left — restarting
# one on reconnect re-runs it for nobody (and, for an extract, re-breaks the agent
# session). Everything NOT listed here is treated as durable and retried:
# backups, maintenance ops (check/prune/compact), and rclone_sync (which owns a
# persistent RcloneSyncJob record and also runs automatically after backups).
# Allowlist, not blocklist, so an unknown/new job kind defaults to the safe side
# (retry) rather than being silently dropped.
REQUEST_SCOPED_REPOSITORY_JOB_KINDS = frozenset(
    {
        "repository.extract_archive_file",
        "repository.list_archive_contents",
        "repository.list_archives",
        "repository.info",
        "repository.init",
    }
)


def _is_request_scoped_repository_job(job: AgentJob) -> bool:
    """True for repository ops whose only receiver is a synchronous request."""
    if job.job_type != "repository":
        return False
    payload = job.payload if isinstance(job.payload, dict) else {}
    return payload.get("job_kind") in REQUEST_SCOPED_REPOSITORY_JOB_KINDS


def _requeue_stale_agent_jobs(
    db: Session,
    current_agent: AgentMachine,
    *,
    now: datetime,
    running_job_ids: list[int],
) -> None:
    running_ids = set(running_job_ids)
    stale_cutoff = now - STALE_AGENT_JOB_REQUEUE_AFTER
    jobs = (
        db.query(AgentJob)
        .filter(
            AgentJob.agent_machine_id == current_agent.id,
            AgentJob.status.in_(("claimed", "running", "cancel_requested")),
        )
        .all()
    )
    for job in jobs:
        if job.id in running_ids:
            continue
        if _job_activity_at(job) > stale_cutoff:
            continue

        if _is_request_scoped_repository_job(job):
            # No client is waiting for the result any more — fail terminally
            # instead of restarting a job whose receiver is gone.
            job.status = "failed"
            job.completed_at = now
            job.updated_at = now
            job.error_message = (
                "Agent session lost before delivery; request-scoped repository "
                "operation failed (no client is waiting for the result)."
            )
            continue

        job.status = "queued"
        job.claimed_at = None
        job.started_at = None
        job.updated_at = now

        backup_job = _get_linked_backup_job(job, db)
        if backup_job and not _is_terminal_backup_status(backup_job.status):
            backup_job.status = "pending"
            backup_job.error_message = None


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


def _get_repository_operation_job(agent_job: AgentJob, db: Session) -> Any | None:
    payload = agent_job.payload or {}
    operation = payload.get("operation") if isinstance(payload, dict) else None
    maintenance_job = (
        operation.get("maintenance_job") if isinstance(operation, dict) else None
    )
    if not isinstance(maintenance_job, dict):
        return None

    kind = str(maintenance_job.get("kind") or "")
    job_id = maintenance_job.get("id")
    model = REPOSITORY_OPERATION_JOB_MODELS.get(kind)
    if not model or not job_id:
        return None
    return db.query(model).filter(model.id == int(job_id)).first()


def _sync_repository_operation_progress(agent_job: AgentJob, db: Session) -> None:
    operation_job = _get_repository_operation_job(agent_job, db)
    if not operation_job:
        return
    if getattr(operation_job, "started_at", None) is None:
        operation_job.started_at = agent_job.started_at or _now_utc()
    operation_job.status = "running"
    if hasattr(operation_job, "progress"):
        operation_job.progress = int(agent_job.progress_percent or 0)
    if hasattr(operation_job, "progress_message") and agent_job.current_file:
        operation_job.progress_message = agent_job.current_file


def _finish_linked_repository_operation_job(
    agent_job: AgentJob,
    db: Session,
    *,
    status_value: str,
    completed_at: datetime,
    error_message: Optional[str] = None,
) -> None:
    operation_job = _get_repository_operation_job(agent_job, db)
    if not operation_job:
        return

    operation_job.status = status_value
    if getattr(operation_job, "started_at", None) is None:
        operation_job.started_at = agent_job.started_at or completed_at
    operation_job.completed_at = completed_at
    operation_job.error_message = error_message
    operation_job.logs = _collect_agent_logs(agent_job, db)
    operation_job.has_logs = bool(operation_job.logs)
    if status_value == "completed" and hasattr(operation_job, "progress"):
        operation_job.progress = 100

    repository = (
        db.query(Repository)
        .filter(Repository.id == operation_job.repository_id)
        .first()
    )
    if repository and status_value == "completed":
        if isinstance(operation_job, CheckJob):
            repository.last_check = completed_at
        elif isinstance(operation_job, CompactJob):
            repository.last_compact = completed_at
        repository.updated_at = _now_utc()


def _get_agent_token_from_websocket(websocket: WebSocket) -> Optional[str]:
    auth_header = websocket.headers.get(AGENT_AUTH_HEADER)
    if not auth_header or not auth_header.startswith("Bearer "):
        return None
    return auth_header.split(" ", 1)[1].strip()


def _mark_agent_job_claimed(job: AgentJob, *, now: Optional[datetime] = None) -> None:
    if job.status != "queued":
        return
    now = now or _now_utc()
    job.status = "claimed"
    job.claimed_at = now
    job.updated_at = now


def _mark_agent_job_started(
    job: AgentJob, db: Session, *, started_at: Optional[datetime] = None
) -> None:
    if job.status in FINAL_AGENT_JOB_STATUSES:
        return
    now = _now_utc()
    if job.claimed_at is None:
        job.claimed_at = now
    if job.started_at is None:
        job.started_at = _normalize_agent_timestamp(started_at)
    if job.status != "cancel_requested":
        job.status = "running"
    backup_job = _get_linked_backup_job(job, db)
    if backup_job:
        backup_job.status = "running"
        if backup_job.started_at is None:
            backup_job.started_at = job.started_at
    else:
        _sync_repository_operation_progress(job, db)
    job.updated_at = now


def _apply_agent_job_progress(
    job: AgentJob, db: Session, progress: dict[str, Any]
) -> None:
    if job.status in FINAL_AGENT_JOB_STATUSES:
        return
    for field_name, value in progress.items():
        if hasattr(job, field_name):
            setattr(job, field_name, value)
    job.progress = progress
    backup_job = _get_linked_backup_job(job, db)
    if backup_job:
        backup_job.status = "running"
        _sync_backup_progress(job, backup_job)
    else:
        _sync_repository_operation_progress(job, db)
    job.updated_at = _now_utc()


def _append_agent_job_log(
    job: AgentJob,
    db: Session,
    *,
    sequence: int,
    stream: str,
    message: str,
    created_at: Optional[datetime] = None,
) -> bool:
    existing_log = (
        db.query(AgentJobLog)
        .filter(
            AgentJobLog.agent_job_id == job.id,
            AgentJobLog.sequence == sequence,
        )
        .first()
    )
    if existing_log:
        return False
    db.add(
        AgentJobLog(
            agent_job_id=job.id,
            sequence=sequence,
            stream=stream,
            message=message,
            created_at=_normalize_agent_timestamp(created_at),
            received_at=_now_utc(),
        )
    )
    job.updated_at = _now_utc()
    return True


def _complete_agent_job(
    job: AgentJob,
    db: Session,
    *,
    result: dict[str, Any],
    completed_at: Optional[datetime] = None,
) -> None:
    if job.status in FINAL_AGENT_JOB_STATUSES:
        return
    completed = _normalize_agent_timestamp(completed_at)
    job.status = "completed"
    job.completed_at = completed
    job.result = result
    job.error_message = None
    job.updated_at = _now_utc()
    _finish_linked_backup_job(job, db, status_value="completed", completed_at=completed)
    _finish_linked_repository_operation_job(
        job, db, status_value="completed", completed_at=completed
    )


def _fail_agent_job(
    job: AgentJob,
    db: Session,
    *,
    error_message: str,
    return_code: Optional[int] = None,
    completed_at: Optional[datetime] = None,
) -> None:
    if job.status in FINAL_AGENT_JOB_STATUSES:
        return
    completed = _normalize_agent_timestamp(completed_at)
    job.status = "failed"
    job.completed_at = completed
    job.error_message = error_message
    job.result = {"return_code": return_code} if return_code is not None else {}
    job.updated_at = _now_utc()
    _finish_linked_backup_job(
        job,
        db,
        status_value="failed",
        completed_at=completed,
        error_message=error_message,
    )
    _finish_linked_repository_operation_job(
        job,
        db,
        status_value="failed",
        completed_at=completed,
        error_message=error_message,
    )


def _cancel_agent_job(
    job: AgentJob, db: Session, *, completed_at: Optional[datetime] = None
) -> None:
    if job.status in FINAL_AGENT_JOB_STATUSES:
        return
    completed = _normalize_agent_timestamp(completed_at)
    job.status = "canceled"
    job.completed_at = completed
    job.updated_at = _now_utc()
    _finish_linked_backup_job(
        job,
        db,
        status_value="cancelled",
        completed_at=completed,
        error_message="Agent job canceled",
    )
    _finish_linked_repository_operation_job(
        job,
        db,
        status_value="cancelled",
        completed_at=completed,
        error_message="Agent job canceled",
    )


async def _dispatch_queued_agent_jobs(db: Session, agent_machine_id: int) -> None:
    jobs = (
        db.query(AgentJob)
        .filter(
            AgentJob.agent_machine_id == agent_machine_id,
            AgentJob.status == "queued",
        )
        .order_by(AgentJob.created_at.asc(), AgentJob.id.asc())
        .all()
    )
    for job in jobs:
        if live_agent_job_kind(job) == "filesystem.browse":
            continue
        await dispatch_agent_job_best_effort(
            db,
            job,
            source="session_reconnect",
        )


def _load_session_job(
    db: Session, agent_machine_id: int, job_id: Any
) -> Optional[AgentJob]:
    if job_id is None:
        return None
    try:
        parsed_job_id = int(job_id)
    except (TypeError, ValueError):
        return None
    return (
        db.query(AgentJob)
        .filter(
            AgentJob.id == parsed_job_id,
            AgentJob.agent_machine_id == agent_machine_id,
        )
        .first()
    )


async def _handle_agent_session_message(
    db: Session,
    agent_machine_id: int,
    message: dict[str, Any],
) -> None:
    message_type = str(message.get("type") or "")
    command_id = str(message.get("command_id") or "")
    job_id = message.get("job_id")

    if message_type == "heartbeat":
        # Idle-liveness signal. The agent stays in recv() and sends this on a
        # timer (even while a job runs in a worker thread), so it is the one
        # signal that keeps last_seen_at fresh when the agent is not actively
        # POSTing /heartbeat during a job. Protocol-level WS pings keep the
        # socket alive but never reach here, so without this an idle-but-healthy
        # agent looks stale.
        now = _now_utc()
        db.query(AgentMachine).filter(AgentMachine.id == agent_machine_id).update(
            {"last_seen_at": now, "status": "online", "updated_at": now},
            synchronize_session=False,
        )
        db.commit()
        return

    job = _load_session_job(db, agent_machine_id, job_id)

    if message_type == "command_ack":
        if job:
            _mark_agent_job_claimed(job)
            db.commit()
        return

    if message_type == "job_started":
        if job:
            _mark_agent_job_started(
                job, db, started_at=_parse_optional_datetime(message.get("started_at"))
            )
            db.commit()
        return

    if message_type == "progress":
        if job:
            progress = {
                key: value
                for key, value in message.items()
                if key
                in {
                    "progress_percent",
                    "current_file",
                    "original_size",
                    "compressed_size",
                    "deduplicated_size",
                    "nfiles",
                    "backup_speed",
                    "total_expected_size",
                    "estimated_time_remaining",
                }
            }
            _apply_agent_job_progress(job, db, progress)
            db.commit()
        return

    if message_type == "log":
        text = str(message.get("message") or "")
        stream = str(message.get("stream") or "stdout")
        sequence = _parse_int(message.get("sequence"), default=0)
        agent_connection_manager.append_log(
            agent_machine_id,
            message=text,
            stream=stream,
            command_id=command_id or None,
            job_id=_parse_int(job_id, default=0) or None,
        )
        if job:
            _append_agent_job_log(
                job,
                db,
                sequence=sequence,
                stream=stream,
                message=text,
                created_at=_parse_optional_datetime(message.get("created_at")),
            )
            db.commit()
        return

    if message_type == "command_result":
        result = message.get("result")
        result_payload = result if isinstance(result, dict) else {}
        if command_id:
            agent_connection_manager.resolve_command(
                agent_machine_id, command_id, result_payload
            )
        agent_connection_manager.append_log(
            agent_machine_id,
            message="Command completed",
            stream="session",
            command_id=command_id or None,
            job_id=int(job_id) if job_id else None,
        )
        if job:
            _complete_agent_job(
                job,
                db,
                result=result_payload,
                completed_at=_parse_optional_datetime(message.get("completed_at")),
            )
            db.commit()
        return

    if message_type == "command_error":
        error_payload = (
            message.get("error") if isinstance(message.get("error"), dict) else {}
        )
        error_message = str(
            error_payload.get("message") or message.get("message") or "Command failed"
        )
        if command_id:
            agent_connection_manager.reject_command(
                agent_machine_id,
                command_id,
                message=error_message,
                payload=error_payload,
            )
        agent_connection_manager.append_log(
            agent_machine_id,
            level="error",
            message=error_message,
            stream="session",
            command_id=command_id or None,
            job_id=int(job_id) if job_id else None,
        )
        if job:
            _fail_agent_job(
                job,
                db,
                error_message=error_message,
                return_code=error_payload.get("return_code"),
                completed_at=_parse_optional_datetime(message.get("completed_at")),
            )
            db.commit()
        return

    if message_type == "job_canceled":
        if job:
            _cancel_agent_job(
                job,
                db,
                completed_at=_parse_optional_datetime(message.get("completed_at")),
            )
            db.commit()
        return

    agent_connection_manager.append_log(
        agent_machine_id,
        level="warning",
        stream="session",
        message=f"Ignored unknown session message type: {message_type}",
    )


def _parse_optional_datetime(value: Any) -> Optional[datetime]:
    if value is None or isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _parse_int(value: Any, *, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


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
        default_path=enrollment_token.default_path,
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
    _requeue_stale_agent_jobs(
        db,
        current_agent,
        now=now,
        running_job_ids=payload.running_job_ids,
    )
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


@router.websocket("/session")
async def session(websocket: WebSocket, db: Session = Depends(get_db)):
    connection: Optional[AgentConnection] = None
    try:
        try:
            current_agent = resolve_agent_from_token(
                _get_agent_token_from_websocket(websocket), db
            )
        except HTTPException as exc:
            await websocket.close(code=1008, reason=str(exc.detail))
            return

        await websocket.accept()
        try:
            raw_hello = await asyncio.wait_for(
                websocket.receive_json(),
                timeout=AGENT_SESSION_HELLO_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            await websocket.close(code=1008, reason="Hello timeout")
            return
        try:
            hello = AgentSessionHello.model_validate(raw_hello)
        except Exception:
            await websocket.close(code=1003, reason="Invalid hello")
            return

        if hello.type != "hello" or hello.agent_id != current_agent.agent_id:
            await websocket.close(code=1008, reason="Agent identity mismatch")
            return

        now = _now_utc()
        current_agent.hostname = hello.hostname or current_agent.hostname
        current_agent.agent_version = hello.agent_version or current_agent.agent_version
        current_agent.borg_versions = hello.borg_versions
        current_agent.capabilities = hello.capabilities
        current_agent.status = "online"
        current_agent.last_error = None
        current_agent.last_seen_at = now
        current_agent.updated_at = now
        _requeue_stale_agent_jobs(
            db,
            current_agent,
            now=now,
            running_job_ids=hello.running_job_ids,
        )
        db.commit()

        connection = AgentConnection(
            agent_machine_id=current_agent.id,
            agent_id=current_agent.agent_id,
            websocket=websocket,
            metadata=hello.model_dump(),
        )
        await agent_connection_manager.register(connection)
        await websocket.send_json(
            {
                "type": "hello_ack",
                "server_time": serialize_datetime(_now_utc()),
            }
        )
        await _dispatch_queued_agent_jobs(db, current_agent.id)

        while True:
            message = await websocket.receive_json()
            if isinstance(message, dict):
                await _handle_agent_session_message(db, current_agent.id, message)
    except WebSocketDisconnect:
        pass
    finally:
        if connection is not None:
            disconnected = await agent_connection_manager.disconnect(
                connection.agent_machine_id, connection
            )
            if disconnected:
                current = (
                    db.query(AgentMachine)
                    .filter(AgentMachine.id == connection.agent_machine_id)
                    .first()
                )
                if current and current.status == "online":
                    current.status = "offline"
                    current.updated_at = _now_utc()
                    db.commit()


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
    else:
        _sync_repository_operation_progress(job, db)
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
    else:
        _sync_repository_operation_progress(job, db)
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
    if job.status in FINAL_AGENT_JOB_STATUSES:
        return AgentJobStatusResponse(id=job.id, status=job.status)

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
    _finish_linked_repository_operation_job(
        job,
        db,
        status_value="completed",
        completed_at=job.completed_at,
    )
    db.commit()

    return AgentJobStatusResponse(id=job.id, status=job.status)


@router.post("/jobs/{job_id}/artifact")
async def upload_job_artifact(
    job_id: int,
    request: Request,
    current_agent: AgentMachine = Depends(get_current_agent),
    db: Session = Depends(get_db),
):
    """Relay a streamed job artifact (e.g. an extracted file) to the waiting
    download consumer without buffering it to disk.

    The download route registers a relay channel before dispatching the job. If
    none is registered the client has already gone (aborted or timed out), so we
    drain and drop the body rather than let the agent block.
    """
    job = _get_agent_job(job_id, current_agent, db)

    if not agent_artifact_relay.is_registered(job.id):
        async for _ in request.stream():
            pass
        return {"accepted": False, "size": 0}

    size = 0
    delivered = True
    try:
        async for chunk in request.stream():
            if not chunk:
                continue
            size += len(chunk)
            if not await agent_artifact_relay.push(job.id, chunk):
                # The download consumer is gone; stop relaying (and stop the
                # agent's upload) instead of draining the whole body for nobody.
                delivered = False
                break
        if delivered:
            await agent_artifact_relay.close(job.id)
    except Exception as exc:
        await agent_artifact_relay.close(job.id, error=str(exc))
        raise

    job.updated_at = _now_utc()
    db.commit()
    return {"accepted": delivered, "size": size}


@router.post("/jobs/{job_id}/fail", response_model=AgentJobStatusResponse)
async def fail_job(
    job_id: int,
    payload: AgentJobFailRequest,
    current_agent: AgentMachine = Depends(get_current_agent),
    db: Session = Depends(get_db),
):
    job = _get_agent_job(job_id, current_agent, db)
    if job.status in FINAL_AGENT_JOB_STATUSES:
        return AgentJobStatusResponse(id=job.id, status=job.status)

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
    _finish_linked_repository_operation_job(
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
    if job.status in FINAL_AGENT_JOB_STATUSES:
        return AgentJobStatusResponse(id=job.id, status=job.status)

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
    _finish_linked_repository_operation_job(
        job,
        db,
        status_value="cancelled",
        completed_at=job.completed_at,
        error_message="Agent job canceled",
    )
    db.commit()

    return AgentJobStatusResponse(id=job.id, status=job.status)
