from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime
from typing import Any, Callable, Mapping, Optional

import structlog
from fastapi import HTTPException, status
from sqlalchemy import update
from sqlalchemy.orm import Session
from sqlalchemy.pool import SingletonThreadPool, StaticPool

from app.database.models import AgentJob, AgentJobLog, AgentMachine, Repository
from app.services.agent_job_dispatcher import dispatch_agent_cancel_if_connected
from app.services.job_admission import (
    OPERATION_BACKUP,
    ensure_repository_admission,
    ignore_active_job,
    operation_for_agent_job_kind,
)
from app.services.operations.backup_facade import (
    admission_ignore_for,
    backup_job_link_columns,
    resolve_backup_job,
)

logger = structlog.get_logger()

EXECUTOR_SERVER = "server"
EXECUTOR_AGENT = "agent"
# `completed_with_warnings`: the agent ran the command through and the
# server classified its Borg warning exit code (`_complete_agent_job`).
TERMINAL_AGENT_STATUSES = {"completed", "completed_with_warnings", "failed", "canceled"}
SUCCESSFUL_AGENT_STATUSES = {"completed", "completed_with_warnings"}
REPOSITORY_OPERATION_CAPABILITIES = {
    "repository.init",
    "repository.info",
    "repository.rinfo",
    "repository.archive_info",
    "repository.list_archives",
    "repository.delete_archive",
    "repository.break_lock",
    "repository.list_archive_contents",
    "repository.extract_archive_file",
    "repository.export_archive_tar",
    "repository.restore",
    "repository.check",
    "repository.prune",
    "repository.compact",
    "repository.rclone_sync",
    "repository.disk_usage",
    "repository.storage_usage",
    "repository.diff",
}
# Kinds whose output the server parses. The agent reports the raw JSON as
# `stdout` and its own parse of it as `data` (its MACHINE_PARSED_JOB_KINDS;
# the two packages share no imports, so the set is stated twice). The reader
# takes the result once, from the wait below, and nothing reads the stored
# copy back, so the row keeps only what still describes the run.
MACHINE_PARSED_JOB_KINDS = frozenset(
    {
        "repository.info",
        "repository.rinfo",
        "repository.archive_info",
        "repository.list_archives",
    }
)
CONSUMED_RESULT_KEYS = ("return_code", "command", "stderr")


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


# The agent job that produces an archive's change listing for the history
# index (agents from 0.1.6).
AGENT_DIFF_JOB_KIND = "repository.diff"


def agent_advertises_job(agent: Any, job_kind: str) -> bool:
    """`agent_supports_job` on an agent row already loaded (a page's
    machines, or the columns the query below selects)."""
    if agent is None or agent.deleted_at is not None:
        return False
    if agent.status in ("disabled", "revoked", "deleted"):
        return False
    return isinstance(agent.capabilities, list) and job_kind in agent.capabilities


def agent_supports_job(
    db: Session,
    repository: Repository,
    job_kind: str,
    *,
    agents: Optional[Mapping[int, AgentMachine]] = None,
) -> bool:
    """True when the repository's agent advertises `job_kind`.

    `agents` is a page's machines by id, loaded once (the repositories hub
    asks per repository on every poll): rows with `capabilities`,
    `deleted_at` and `status`; single-repository callers leave it out and
    query.

    Agents report their capabilities on hello and heartbeat, so an agent
    from before a job kind existed answers False until it is updated; so
    does a repository with no agent assigned, and one whose agent is
    disabled, revoked or deleted, which the admission refuses every job
    (`validate_agent_repository_operation`): the job it once advertised is
    not on offer. Whether the agent is online is a question for the moment
    the job is queued, not for this one.
    """
    if not repository.agent_machine_id:
        return False
    if agents is not None:
        return agent_advertises_job(agents.get(repository.agent_machine_id), job_kind)
    row = (
        db.query(
            AgentMachine.capabilities, AgentMachine.deleted_at, AgentMachine.status
        )
        .filter(AgentMachine.id == repository.agent_machine_id)
        .one_or_none()
    )
    return agent_advertises_job(row, job_kind)


def agent_timezone_for_repository(db: Session, repository: Repository) -> Optional[str]:
    """The IANA zone the repository's agent reported, if any.

    Borg renders archive times in the local zone of the process that produced
    the listing; for an agent-executed repository that is the agent, so its
    reported (current) zone is the one to interpret those times with. None for
    non-agent repositories and for agents that never reported a zone.
    """
    if not is_agent_executor(repository) or not repository.agent_machine_id:
        return None
    agent = (
        db.query(AgentMachine)
        .filter(AgentMachine.id == repository.agent_machine_id)
        .first()
    )
    return agent.timezone if agent else None


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
        # Since phase 5 every maintenance job is an `operations` row. The
        # legacy `*_jobs` ids are an independent sequence, so the table is
        # named: a payload without it was written before the upgrade and
        # names a legacy row.
        operation_payload["maintenance_job"] = {
            "kind": maintenance_job_kind,
            "id": maintenance_job_id,
            "table": "operations",
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
    if agent.deleted_at is not None or agent.status in (
        "disabled",
        "revoked",
        "deleted",
    ):
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
    if agent.deleted_at is not None or agent.status in (
        "disabled",
        "revoked",
        "deleted",
    ):
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


def _require_repository_lane(
    db: Session, repository: Repository, maintenance_job_id: Optional[int]
) -> None:
    """Refuse to leave queued operations out of admission unless the caller's
    maintenance row holds the repository lane: a running operation of an
    exclusive kind on this repository. While it runs, no queued exclusive
    operation of the repository can start (`lanes.lane_free`), and any other
    queued operation that starts goes through admission itself. From
    anywhere else a queued prune would simply stop being counted, so this
    is a programming error and fails loudly."""
    from app.database.models import Operation
    from app.services.operations.vocab import is_exclusive

    row = db.get(Operation, maintenance_job_id) if maintenance_job_id else None
    if (
        row is None
        or row.repository_id != repository.id
        or row.status != "running"
        or not is_exclusive(row.kind)
    ):
        raise RuntimeError(
            "ignore_queued_operations is only valid for a running exclusive "
            "operation of the repository (the runner's repository lane)"
        )


def queue_agent_repository_operation_job(
    db: Session,
    repository: Repository,
    *,
    job_kind: str,
    operation: Optional[dict[str, Any]] = None,
    maintenance_job_kind: Optional[str] = None,
    maintenance_job_id: Optional[int] = None,
    ignore_queued_operations: bool = False,
) -> AgentJob:
    """`ignore_queued_operations` (see `list_active_repository_work`) is only
    valid from the runner's repository lane, and is refused anywhere else:
    see `_require_repository_lane`."""
    if ignore_queued_operations:
        _require_repository_lane(db, repository, maintenance_job_id)
    agent = validate_agent_repository_operation(db, repository, job_kind=job_kind)
    operation_payload = operation
    admission_operation = operation_for_agent_job_kind(job_kind)
    # Phase 5 moved every maintenance kind to `operations`. The value is the
    # table admission should ignore, so the row this caller just created
    # cannot block its own admission.
    ensure_repository_admission(
        db,
        repository,
        admission_operation,
        ignore=ignore_active_job(
            "operations" if maintenance_job_kind else None,
            maintenance_job_id,
        ),
        ignore_queued_operations=ignore_queued_operations,
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


def get_agent_archive_browse_job(
    db: Session,
    repository: Repository,
    agent_job_id: int,
    archive_name: str,
) -> Optional[AgentJob]:
    """Return a previously-queued ``list_archive_contents`` job iff it belongs to
    this repository and archive.

    Archive browsing is asynchronous: the first request queues the job and the
    client then polls with the returned job id. This validates that a polled job
    id really is this repository's browse job for this archive, so one viewer
    cannot poll another repository's listing by guessing an id.
    """
    agent_job = db.query(AgentJob).filter(AgentJob.id == agent_job_id).first()
    if agent_job is None:
        return None
    payload = agent_job.payload if isinstance(agent_job.payload, dict) else {}
    repository_matches = (payload.get("repository") or {}).get("id") == repository.id
    kind_matches = payload.get("job_kind") == "repository.list_archive_contents"
    archive_matches = (payload.get("operation") or {}).get("archive") == archive_name
    return (
        agent_job if repository_matches and kind_matches and archive_matches else None
    )


# How many of a failed job's last log rows to read for its reason. Borg prints
# a usage block before the line that says what was actually wrong, and each
# line arrives as its own row.
FAILURE_LOG_TAIL = 40


def _log_reason_line(rows: list, *, stream: Optional[str]) -> Optional[str]:
    """The reason line from the job's newest log row on `stream` (any stream
    when it is None), given `rows` ordered newest first.

    A row's first non-empty line is the reason: borg leads with the human
    sentence and follows it with a traceback.

    Sequence 0 is the agent's own "Starting <kind>: <command>" preamble, never
    a reason - it is what the job was about to run, not why it stopped.
    """
    for sequence, row_stream, message in rows:
        if sequence == 0 or (stream is not None and row_stream != stream):
            continue
        lines = [line.strip() for line in (message or "").splitlines() if line.strip()]
        if lines:
            return lines[0]
    return None


def _agent_job_failure_message(db: Session, agent_job: AgentJob) -> Optional[str]:
    """The agent only reports "exited with code N"; borg's actual reason is in
    the job log.

    Prefer stderr, but fall back to stdout: borg prints an argument error
    ("invalid choice: ...") on stdout, and reporting only the exit code there
    leaves the operator with nothing to act on.
    """
    rows = (
        db.query(AgentJobLog.sequence, AgentJobLog.stream, AgentJobLog.message)
        .filter(AgentJobLog.agent_job_id == agent_job.id)
        .order_by(AgentJobLog.sequence.desc())
        .limit(FAILURE_LOG_TAIL)
        .all()
    )
    reason = _log_reason_line(rows, stream="stderr") or _log_reason_line(
        rows, stream=None
    )
    if not reason:
        return agent_job.error_message
    if not agent_job.error_message:
        return reason
    return f"{agent_job.error_message}: {reason}"


def agent_operation_failed_detail(reason: Optional[str]) -> dict[str, Any]:
    """The error detail for a failed agent repository operation.

    The reason belongs in `params`, not in a `message` key: the frontend renders
    a detail by translating its key with its params and drops every other field,
    so a `message` never reaches the operator - which is how borg's actual
    complaint used to surface as a bare "The agent repository operation failed".
    """
    reason = (reason or "").strip()
    if not reason:
        return {"key": "backend.errors.agents.repositoryOperationFailed"}
    return {
        "key": "backend.errors.agents.repositoryOperationFailedWithReason",
        "params": {"reason": reason},
    }


def is_machine_parsed_job(agent_job: AgentJob) -> bool:
    payload = agent_job.payload if isinstance(agent_job.payload, dict) else {}
    return payload.get("job_kind") in MACHINE_PARSED_JOB_KINDS


def consumed_result(result: Any) -> dict[str, Any]:
    """A machine-parsed result as the row keeps it once its reader has it:
    `stdout` and `data` (the same output twice) are gone, the rest stays."""
    if not isinstance(result, dict):
        return {}
    return {key: result[key] for key in CONSUMED_RESULT_KEYS if key in result}


def drop_consumed_agent_job_output(db: Session, agent_job: AgentJob) -> None:
    """Reduce a machine-parsed job's stored result once the wait handed it over.

    A listing is the largest thing a repository job row holds and every reader
    keeps its own copy, yet the row kept the full one until the job fell out
    of retention. The write goes through a session of its own on the caller's
    engine: the caller's transaction is neither committed nor rolled back by
    it, and the caller's copy of the result is untouched. A pool that hands
    every session the same connection (in-memory SQLite) cannot give the
    write a transaction of its own, so the row is left to the retention pass
    there. Best effort, like the browse route's drop of a consumed contents
    listing: a failed write is logged, and the retention pass reduces what is
    left behind.
    """
    result = agent_job.result
    if not is_machine_parsed_job(agent_job) or not isinstance(result, dict):
        return
    if "stdout" not in result and "data" not in result:
        return
    engine = db.get_bind()
    if isinstance(engine.pool, (SingletonThreadPool, StaticPool)):
        return
    agent_job_id = agent_job.id
    try:
        with Session(bind=engine) as own:
            own.execute(
                update(AgentJob)
                .where(AgentJob.id == agent_job_id)
                .values(result=consumed_result(result))
            )
            own.commit()
    except Exception as exc:
        # the exception text can carry the bound parameters, stderr included
        logger.warning(
            "consumed agent job result could not be reduced",
            agent_job_id=agent_job_id,
            error_type=type(exc).__name__,
        )


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
        if agent_job.status in SUCCESSFUL_AGENT_STATUSES:
            # The caller gets the full result; the row keeps the small part.
            result = agent_job.result or {}
            drop_consumed_agent_job_output(db, agent_job)
            return result
        if agent_job.status in TERMINAL_AGENT_STATUSES:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=agent_operation_failed_detail(
                    _agent_job_failure_message(db, agent_job)
                ),
            )
        await asyncio.sleep(poll_interval_seconds)

    raise HTTPException(
        status_code=status.HTTP_504_GATEWAY_TIMEOUT,
        detail={"key": "backend.errors.agents.repositoryOperationTimeout"},
    )


# `agent_jobs.job_type` of the row that carries a backup to its agent. Named
# once: the writers set it and `get_agent_job_for_backup` reads it, and a
# mismatch between them fails silently — the cancel route would find no job
# and refuse, the log endpoints would serve nothing.
BACKUP_AGENT_JOB_TYPE = "backup"


def queue_agent_backup_job(
    db: Session,
    backup_job,
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
        ignore=admission_ignore_for(backup_job),
    )

    archive_name = archive_name or (
        f"manual-backup-{datetime.now().strftime('%Y-%m-%dT%H:%M:%S')}"
    )
    backup_job.execution_mode = EXECUTOR_AGENT
    backup_job.archive_name = archive_name

    now = datetime.utcnow()
    agent_job = AgentJob(
        agent_machine_id=agent.id,
        job_type=BACKUP_AGENT_JOB_TYPE,
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
        **backup_job_link_columns(db, backup_job.id),
    )
    db.add(agent_job)
    db.commit()
    db.refresh(agent_job)
    return agent_job


SCRIPT_RUN_CAPABILITY = "script.run"


def build_agent_script_payload(
    script_name: str, env: Optional[dict[str, str]] = None
) -> dict[str, Any]:
    """Payload for a ``script.run`` agent job. Carries only the script *name*
    (never a path) and the ``BORG_UI_*`` context env — the agent resolves the
    name against its own allow-list."""
    return {
        "schema_version": 1,
        "job_kind": "script.run",
        "script": {"name": script_name},
        "env": {
            key: str(value)
            for key, value in (env or {}).items()
            if isinstance(key, str)
        },
    }


def validate_agent_script(agent: AgentMachine) -> None:
    """Ensure the agent is queueable and advertises the ``script.run`` capability."""
    if agent.deleted_at is not None or agent.status in (
        "disabled",
        "revoked",
        "deleted",
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"key": "backend.errors.agents.agentNotQueueable"},
        )
    if SCRIPT_RUN_CAPABILITY not in (agent.capabilities or []):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "key": "backend.errors.agents.capabilityMissing",
                "params": {"capability": SCRIPT_RUN_CAPABILITY},
            },
        )


def queue_agent_script_job(
    db: Session,
    agent: AgentMachine,
    *,
    script_name: str,
    env: Optional[dict[str, str]] = None,
) -> AgentJob:
    """Enqueue a ``script.run`` job for a resolved agent. Not a borg operation, so
    it carries no repository admission — it wraps a plan run, not the borg call.

    It carries no backup link either. `agent_jobs` has one link column,
    `operation_id`, and every reader of it — the agent's own reports, the
    reaper, the cancel path — takes the row it points at to *be* that
    operation's transport job: a script row wearing the same link would
    fail a finished backup, overwrite its log and be cancelled in its
    place. What ties a hook to the run it belongs to is its
    `script_executions` row, through the plan run and the `agent_job_id`
    the caller writes back onto it.
    """
    validate_agent_script(agent)
    now = datetime.utcnow()
    agent_job = AgentJob(
        agent_machine_id=agent.id,
        job_type="script",
        status="queued",
        payload=build_agent_script_payload(script_name, env),
        created_at=now,
        updated_at=now,
    )
    db.add(agent_job)
    db.commit()
    db.refresh(agent_job)
    return agent_job


def _terminate_agent_script_job(
    db: Session, agent_job: AgentJob, error_message: str
) -> None:
    """Move a ``script.run`` job to the non-dispatchable terminal ``canceled``
    state and commit, so an offline agent's fallback dispatch cannot run the
    script after the plan was cancelled or timed out. Remote cancellation stays
    best-effort; this is the local guarantee that the job never fires later."""
    if agent_job.status not in TERMINAL_AGENT_STATUSES:
        agent_job.status = "canceled"
        if error_message and not agent_job.error_message:
            agent_job.error_message = error_message
        db.commit()


async def wait_for_agent_script_job(
    db: Session,
    agent_job_id: int,
    *,
    is_cancelled: Optional[Callable[[], bool]] = None,
    timeout_seconds: Optional[float] = None,
    poll_interval_seconds: float = 0.5,
) -> dict[str, Any]:
    """Poll a ``script.run`` agent job to a terminal state and return a snapshot
    ``{status, result, error_message}`` — never raises for a script failure, so
    the plan hook policy (skip/continue/fail) decides in the caller. ``status`` is
    ``"timeout"`` if the deadline passes first."""
    deadline = None if timeout_seconds is None else time.monotonic() + timeout_seconds
    while True:
        db.expire_all()
        agent_job = db.query(AgentJob).filter(AgentJob.id == agent_job_id).first()
        if not agent_job:
            return {"status": "failed", "result": {}, "error_message": "job not found"}

        if (
            is_cancelled
            and is_cancelled()
            and agent_job.status not in TERMINAL_AGENT_STATUSES
        ):
            # Best-effort remote cancel, then persist a terminal state so the job
            # can never be dispatched (and the script run) after cancellation.
            await dispatch_agent_cancel_if_connected(agent_job)
            _terminate_agent_script_job(db, agent_job, "canceled")
            return {
                "status": "canceled",
                "result": agent_job.result or {},
                "error_message": agent_job.error_message,
            }

        if agent_job.status in TERMINAL_AGENT_STATUSES:
            return {
                "status": agent_job.status,
                "result": agent_job.result or {},
                "error_message": agent_job.error_message,
            }

        if deadline is not None and time.monotonic() > deadline:
            # Same guarantee on timeout: an offline agent must not run the script
            # later via fallback dispatch once the plan gave up waiting.
            await dispatch_agent_cancel_if_connected(agent_job)
            _terminate_agent_script_job(db, agent_job, "agent script timed out")
            return {
                "status": "timeout",
                "result": agent_job.result or {},
                "error_message": "agent script timed out",
            }

        await asyncio.sleep(poll_interval_seconds)


def get_agent_job_for_backup(db: Session, backup_job: Any) -> Optional[AgentJob]:
    """The transport job that carries a backup to its agent.

    `agent_jobs` has one link column, so the lookup names the kind it wants
    rather than trusting the link alone: the caller cancels this job, reads
    its logs and decides the backup's fate from its status, none of which
    may land on a row that merely belongs to the same run.
    """
    return (
        db.query(AgentJob)
        .filter(
            AgentJob.operation_id == backup_job.id,
            AgentJob.job_type == BACKUP_AGENT_JOB_TYPE,
        )
        .order_by(AgentJob.id.desc())
        .first()
    )


# A job moves queued -> claimed -> running -> terminal, so two lost races are
# the most a live job can cost; the bound only guards against a pathological
# writer flipping the row back and forth.
ABANDON_ATTEMPTS = 4


def abandon_agent_repository_operation_job(
    db: Session, agent_job_id: int, *, now: Optional[datetime] = None
) -> Optional[AgentJob]:
    """Take a repository job the caller stopped waiting for out of the
    admission's way.

    A job nobody claimed is cancelled outright: the reaper only reaps
    in-flight jobs, so a queued job of an unresponsive agent would count as
    active work for every later request on the repository until the agent
    reconnects and runs the stale job. A claimed or running job gets
    cancel_requested and the agent ends it. Terminal jobs are left alone.
    Returns the job, or None when it no longer exists.
    """
    agent_job = db.query(AgentJob).filter(AgentJob.id == agent_job_id).first()
    if agent_job is None:
        return None
    now = now or datetime.utcnow()
    # Conditional on the status just read, and retried while the job is
    # still live: the agent's reports land concurrently. A completion must
    # not turn back into cancel_requested (admission counts that as
    # active); a claim or start between read and write must still get the
    # cancel, so a lost race re-reads and writes for the new state.
    for _ in range(ABANDON_ATTEMPTS):
        observed = agent_job.status
        if observed == "queued":
            values = {
                "status": "canceled",
                "completed_at": now,
                "error_message": (
                    "Abandoned by server: the agent did not pick the job up in time"
                ),
                "updated_at": now,
            }
        elif observed in ("claimed", "running"):
            values = {"status": "cancel_requested", "updated_at": now}
        else:
            return agent_job
        changed = (
            db.query(AgentJob)
            .filter(AgentJob.id == agent_job.id, AgentJob.status == observed)
            .update(values, synchronize_session=False)
        )
        db.commit()
        db.refresh(agent_job)
        if changed:
            return agent_job
    return agent_job


def cancel_unclaimed_agent_repository_job(db: Session, agent_job_id: int) -> None:
    """Cancel a repository job the caller stopped waiting for (a 504 from the
    wait) if no agent has taken it yet.

    Left queued, the job is the duplicate every later request on the
    repository is refused for, with no bound: the reaper never reaps a
    queued job. A job the agent claimed or runs is left alone: the work is
    the agent's (a long `borg info` cache build outlives the server's
    patience and warms the next attempt), and if the agent is gone the
    reaper reaps the job after its window. Never raises: the callers hold no
    pending session state at this point, so a failed commit is rolled back
    and logged, and the caller leaves with the timeout it came with."""
    now = datetime.utcnow()
    try:
        db.query(AgentJob).filter(
            AgentJob.id == agent_job_id, AgentJob.status == "queued"
        ).update(
            {
                "status": "canceled",
                "completed_at": now,
                "error_message": (
                    "Abandoned by server: the agent did not pick the job up in time"
                ),
                "updated_at": now,
            },
            synchronize_session=False,
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.warning(
            "agent job could not be cancelled",
            agent_job_id=agent_job_id,
            error=str(exc),
        )


def cancel_agent_backup_job(
    db: Session, backup_job, *, now: Optional[datetime] = None
) -> tuple[AgentJob, bool]:
    agent_job = get_agent_job_for_backup(db, backup_job)
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
        backup_job = resolve_backup_job(db, backup_job_id)
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
