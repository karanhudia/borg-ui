from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session
import structlog
from typing import Any, List, Literal, Optional
import os  # noqa: F401
from datetime import datetime, timezone

from app.database.models import User, Repository
from app.database.database import get_db
from app.core.borg_errors import (
    get_exit_code_message,
    is_borg_warning_exit_code,
    is_lock_contention_exit_code,
)
from app.core.borg_router import BorgRouter
from app.core.permissions import REPOSITORY_ACTION_RULES
from app.core.security import (
    get_current_user,
    check_repo_access,
    require_repository_access_by_path,
)
from app.services.log_policy import get_log_save_policy, job_has_logs_by_policy
from app.services.operations.details import restore_details
from app.services.operations.enqueue import enqueue, wake_runner
from app.services.operations.restore_facade import (
    CANCELLED_BY_USER,
    CANCELLED_PROCESS_NOT_FOUND,
    list_restore_jobs,
    resolve_restore_job,
)
from app.services.operations.runner import operation_runner
from app.services.agent_job_dispatcher import (
    dispatch_agent_cancel_if_connected,
    dispatch_agent_job_best_effort,
)
from app.services.repository_executor import (
    AGENT_RESTORE_DRY_RUN_JOB_KIND,
    _tail_reason_line,
    abandon_agent_repository_operation_job,
    agent_supports_job,
    is_agent_executor,
    queue_agent_repository_operation_job,
    wait_for_agent_repository_operation_job,
)
from app.services.restore_service import restore_service
from app.utils.datetime_utils import serialize_datetime
from app.utils.redaction import redact_secrets
from app.utils.local_paths import is_restore_destination_allowed
from app.utils.borg_env import (
    get_standard_ssh_opts,
    REQUEST_LOCK_WAIT,
    setup_borg_env,
    cleanup_temp_key_file,
)
from app.utils.ssh_utils import (
    resolve_repo_ssh_key_file,
    resolve_repository_ssh_connection,
)  # Backward-compatible patch target for tests
from app.utils.borg_arguments import validate_operand

logger = structlog.get_logger()
router = APIRouter()


RESTORE_ROLE = REPOSITORY_ACTION_RULES["restore"]


def _require_restore_job_access(
    db: Session, user: User, job: Any, required_role: str
) -> None:
    """Raise 403 unless `user` holds `required_role` on the job's repository.

    Looked up by the job's repository_id. A job whose repository is gone is
    visible to admins only.
    """
    if user.role == "admin":
        return
    repo_id = getattr(job, "repository_id", None)
    repo = db.get(Repository, repo_id) if repo_id is not None else None
    if repo is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"key": "backend.errors.auth.notEnoughPermissions"},
        )
    check_repo_access(db, user, repo, required_role)


def _require_allowed_local_destination(
    restore_request: "RestoreRequest", repository: Repository, user: User
) -> None:
    # An agent repository restores on the agent's host, where no mount points
    # confine a path: only administrators choose a destination there.
    if is_agent_executor(repository):
        if user.role != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"key": "backend.errors.auth.notEnoughPermissions"},
            )
        return
    # SSH destinations write on another host; only a restore that lands on this
    # server is checked. Admins set up the mounts themselves, so only other
    # users are confined to the mount points.
    if restore_request.destination_type == "ssh":
        return
    if not is_restore_destination_allowed(
        restore_request.destination,
        restore_request.paths,
        restore_request.restore_layout,
        confine_to_mounts=user.role != "admin",
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "key": "backend.errors.restore.destinationNotAllowed",
                "params": {"path": restore_request.destination},
            },
        )


def _restore_job_logs_visible(job: Any, log_save_policy: str, logs: Any) -> bool:
    return job_has_logs_by_policy(
        job,
        log_save_policy,
        output_text=[logs, job.error_message],
    )


def _build_repo_env(repo: Repository, db: Session):
    temp_key_file = resolve_repo_ssh_key_file(repo, db)
    ssh_opts = get_standard_ssh_opts(
        include_key_path=temp_key_file,
        connection=resolve_repository_ssh_connection(repo, db),
        db=db,
    )
    env = setup_borg_env(
        passphrase=repo.passphrase, ssh_opts=ssh_opts, lock_wait=REQUEST_LOCK_WAIT
    )
    return env, temp_key_file


class RestorePathMetadata(BaseModel):
    path: str
    type: Literal["file", "directory"]


class RestoreRequest(BaseModel):
    @field_validator("archive")
    @classmethod
    def validate_archive(cls, value: str) -> str:
        return validate_operand(value, "archive selector")

    @field_validator("paths")
    @classmethod
    def validate_paths(cls, values: List[str]) -> List[str]:
        for value in values:
            validate_operand(value, "restore path", archive_path=True)
        return values

    repository: str
    archive: str
    paths: List[str]
    destination: str
    repository_id: int  # Repository ID for fetching repository details
    destination_type: str = "local"  # 'local' or 'ssh'
    destination_connection_id: Optional[int] = (
        None  # SSH connection ID for SSH destinations
    )
    restore_layout: Literal["preserve_path", "contents_only"] = "preserve_path"
    path_metadata: List[RestorePathMetadata] = Field(default_factory=list)
    # "refuse": exact restore, a Borg 2 destination that holds anything is
    # refused; "continue": write into it (Borg 2's --continue, #1261)
    existing_files: Literal["refuse", "continue"] = "refuse"


def _restore_path_metadata_to_dict(item: RestorePathMetadata) -> dict:
    if hasattr(item, "model_dump"):
        return item.model_dump()
    return item.dict()


async def _agent_restore_preview(
    db: Session, repo: Repository, restore_request: RestoreRequest
) -> dict:
    """An agent repository's restore preview: the extract dry run, on its
    agent (`repository.restore_dry_run`). The answer is the last lines Borg
    printed, as the server's own preview answers with Borg's output. An
    agent from before the job is refused, as before it existed.

    A wait that ends without the job's verdict (the timeout, a client that
    left) takes the job back: the dry run reads every chunk of the selected
    paths and must not go on for nobody."""
    if not agent_supports_job(db, repo, AGENT_RESTORE_DRY_RUN_JOB_KIND):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"key": "backend.errors.restore.agentPreviewUnsupported"},
        )
    from app.api.archives import _archive_extract_selector
    from app.api.repositories import get_operation_timeouts

    agent_job = queue_agent_repository_operation_job(
        db,
        repo,
        job_kind=AGENT_RESTORE_DRY_RUN_JOB_KIND,
        operation={
            # a Borg 2 archive id names one archive only as `aid:`
            "archive": _archive_extract_selector(restore_request.archive, repo),
            "paths": list(restore_request.paths),
        },
    )
    try:
        await dispatch_agent_job_best_effort(db, agent_job, repository_id=repo.id)
        result = await wait_for_agent_repository_operation_job(
            db,
            agent_job.id,
            timeout_seconds=get_operation_timeouts(db)["backup_timeout"],
        )
    except BaseException:
        # a job that is over is left as it is
        abandoned = abandon_agent_repository_operation_job(db, agent_job.id)
        if abandoned is not None and abandoned.status == "cancel_requested":
            await dispatch_agent_cancel_if_connected(abandoned)
        raise
    return {"preview": result.get("output") or ""}


def _server_preview_answer(result: dict) -> dict:
    """A server repository's preview answer from its extract dry run, as an
    agent repository's: Borg's output, a warning (a path that matched
    nothing) included, for a run that went through; a failure with Borg's
    reason for one that did not (or could not start)."""
    return_code = result.get("return_code")
    stdout = (result.get("stdout") or "").rstrip("\n")
    stderr = (result.get("stderr") or "").rstrip("\n")
    if return_code == 0 or is_borg_warning_exit_code(return_code):
        return {"preview": "\n".join(part for part in (stdout, stderr) if part)}

    reason = _tail_reason_line(
        stderr if stderr.strip() else stdout,
        lock_contention=is_lock_contention_exit_code(return_code),
    )
    if not reason:
        reason = (
            get_exit_code_message(return_code)
            if isinstance(return_code, int)
            else "Borg did not run"
        )
    logger.warning("Restore preview failed", return_code=return_code, reason=reason)
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail={
            "key": "backend.errors.restore.failedPreviewRestoreWithReason",
            "params": {"reason": redact_secrets(reason)},
        },
    )


@router.post("/preview")
async def preview_restore(
    restore_request: RestoreRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Preview a restore operation"""
    try:
        # Get repository details for bypass_lock flag
        repo = require_repository_access_by_path(
            db,
            current_user,
            restore_request.repository,
            RESTORE_ROLE,
        )
        if is_agent_executor(repo):
            # The preview is Borg's extract dry run: on the agent, never on
            # the server.
            return await _agent_restore_preview(db, repo, restore_request)

        if (
            repo.repository_type == "ssh"
            or repo.path.startswith("ssh://")
            or repo.connection_id
        ):
            env, temp_key_file = _build_repo_env(repo, db)
            try:
                result = await BorgRouter(repo).preview_restore(
                    archive=restore_request.archive,
                    paths=restore_request.paths,
                    env=env,
                )
            finally:
                cleanup_temp_key_file(temp_key_file)
        else:
            result = await BorgRouter(repo).preview_restore(
                archive=restore_request.archive,
                paths=restore_request.paths,
            )
        return _server_preview_answer(result)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to preview restore", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"key": "backend.errors.restore.failedPreviewRestore"},
        )


@router.post("/start")
async def start_restore(
    restore_request: RestoreRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Start a restore operation and return job ID"""
    try:
        # Fetch repository to determine repository_type
        repository = (
            db.query(Repository)
            .filter(Repository.id == restore_request.repository_id)
            .first()
        )
        if not repository:
            raise HTTPException(
                status_code=404,
                detail={"key": "backend.errors.restore.repositoryNotFound"},
            )
        check_repo_access(db, current_user, repository, RESTORE_ROLE)
        _require_allowed_local_destination(restore_request, repository, current_user)

        # Validate scenario: SSH repository → SSH destination is not supported
        if (
            repository.repository_type == "ssh"
            and restore_request.destination_type == "ssh"
        ):
            raise HTTPException(
                status_code=400,
                detail={"key": "backend.errors.restore.sshToSshNotSupported"},
            )

        # Determine execution_mode based on repository_type + destination_type
        execution_mode = (
            f"{repository.repository_type}_to_{restore_request.destination_type}"
        )

        # Fetch destination hostname if SSH destination
        destination_hostname = None
        if restore_request.destination_connection_id is not None:
            from app.database.models import SSHConnection

            # Writing through a saved SSH connection needs a global operator,
            # on top of the operator role on the repository checked above.
            if current_user.role not in ("admin", "operator"):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={"key": "backend.errors.restore.operatorAccessRequired"},
                )
            destination_connection = db.get(
                SSHConnection, restore_request.destination_connection_id
            )
            if destination_connection is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail={"key": "backend.errors.ssh.sshConnectionNotFound"},
                )
            destination_hostname = destination_connection.host

        # Phase 7: the row is an operation (spec 6.1) with its restore columns
        # on the details row (spec 6.2). The runner dispatches it (spec 7.1);
        # this route spawns nothing of its own.
        operation = enqueue(
            db,
            "restore",
            repository_id=repository.id,
            trigger="manual",
            params={
                "archive_name": restore_request.archive,
                "paths": list(restore_request.paths),
                "restore_layout": restore_request.restore_layout,
                "existing_files": restore_request.existing_files,
                "path_metadata": [
                    _restore_path_metadata_to_dict(item)
                    for item in restore_request.path_metadata
                ],
            },
            triggered_by_user_id=current_user.id,
            execution_mode="agent" if is_agent_executor(repository) else "server",
            commit=False,
        )
        details = restore_details(db, operation)
        details.archive = restore_request.archive
        details.destination = restore_request.destination
        details.destination_type = restore_request.destination_type
        details.destination_connection_id = restore_request.destination_connection_id
        details.destination_hostname = destination_hostname
        details.repository_type = repository.repository_type
        db.commit()
        wake_runner()

        logger.info(
            "Restore job created",
            job_id=operation.id,
            user=current_user.username,
            execution_mode=execution_mode,
            restore_layout=restore_request.restore_layout,
        )

        return {
            "job_id": operation.id,
            "status": "pending",
            "message": "backend.success.restore.restoreJobStarted",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to start restore", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "key": "backend.errors.restore.failedStartRestore",
                "params": {"error": str(e)},
            },
        )


@router.get("/jobs")
def get_restore_jobs(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    limit: int = 50,
):
    """Get all restore jobs (most recent first)"""
    try:
        jobs = list_restore_jobs(db, limit)
        visible_jobs = []
        for job in jobs:
            try:
                _require_restore_job_access(db, current_user, job, "viewer")
                visible_jobs.append(job)
            except HTTPException:
                continue

        log_save_policy = get_log_save_policy(db)
        payload = []
        for job in visible_jobs:
            # One read per job. An operation keeps its log in a file (spec
            # 6.1), so every use of `job.logs` is disk IO, and this route is
            # polled every few seconds while the Archives page is open.
            logs = job.logs
            payload.append(
                {
                    "id": job.id,
                    "repository": job.repository,
                    "archive": job.archive,
                    "destination": job.destination,
                    "status": job.status,
                    "started_at": serialize_datetime(job.started_at),
                    "completed_at": serialize_datetime(job.completed_at),
                    "progress": job.progress,
                    "error_message": job.error_message,
                    "logs": (
                        logs
                        if _restore_job_logs_visible(job, log_save_policy, logs)
                        else None
                    ),
                    "progress_details": {
                        "nfiles": job.nfiles or 0,
                        "current_file": job.current_file or "",
                        "progress_percent": job.progress_percent or 0.0,
                        "restore_speed": job.restore_speed or 0.0,
                        "estimated_time_remaining": job.estimated_time_remaining or 0,
                    },
                }
            )
        return {"jobs": payload}
    except Exception as e:
        logger.error("Failed to get restore jobs", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"key": "backend.errors.restore.failedGetRestoreJobs"},
        )


@router.get("/status/{job_id}")
def get_restore_status(
    job_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get restore job status"""
    try:
        job = resolve_restore_job(db, job_id)
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"key": "backend.errors.restore.restoreJobNotFound"},
            )
        _require_restore_job_access(db, current_user, job, "operator")
        log_save_policy = get_log_save_policy(db)
        logs = job.logs

        return {
            "id": job.id,
            "repository": job.repository,
            "archive": job.archive,
            "destination": job.destination,
            "status": job.status,
            "started_at": serialize_datetime(job.started_at),
            "completed_at": serialize_datetime(job.completed_at),
            "progress": job.progress,
            "error_message": job.error_message,
            "logs": logs
            if _restore_job_logs_visible(job, log_save_policy, logs)
            else None,
            "progress_details": {
                "nfiles": job.nfiles or 0,
                "current_file": job.current_file or "",
                "progress_percent": job.progress_percent or 0.0,
                "restore_speed": job.restore_speed or 0.0,
                "estimated_time_remaining": job.estimated_time_remaining or 0,
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get restore status", job_id=job_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"key": "backend.errors.restore.failedGetRestoreStatus"},
        )


@router.post("/cancel/{job_id}")
async def cancel_restore(
    job_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Cancel a running restore job"""
    try:
        job = resolve_restore_job(db, job_id)
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"key": "backend.errors.restore.restoreJobNotFound"},
            )
        _require_restore_job_access(db, current_user, job, "operator")

        if job.status != "running":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"key": "backend.errors.restore.canOnlyCancelRunningJobs"},
            )

        # Order matters. The runner's flag has to be raised while the row is
        # still `running` (request_cancel refuses any other status), and it is
        # what makes the executor keep `cancelled` if the service writes
        # `failed` for the killed process a moment later (spec 7.7). A
        # pre-phase-7 row has no operation and no task; request_cancel
        # answers False for it and the legacy write below still applies.
        await operation_runner.request_cancel(job_id)
        process_killed = await restore_service.cancel_restore(job_id)

        job.status = "cancelled"
        job.completed_at = datetime.now(timezone.utc)
        job.error_message = (
            CANCELLED_BY_USER if process_killed else CANCELLED_PROCESS_NOT_FOUND
        )
        db.commit()

        logger.info(
            "Restore cancelled",
            job_id=job_id,
            user=current_user.username,
            process_killed=process_killed,
        )
        return {
            "message": "backend.success.restore.restoreCancelled",
            "process_terminated": process_killed,
        }
    except HTTPException:
        raise  # Re-raise HTTP exceptions to preserve status codes
    except Exception as e:
        logger.error("Failed to cancel restore", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"key": "backend.errors.restore.failedCancelRestore"},
        )
