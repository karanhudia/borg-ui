import asyncio
import base64
import binascii
import json
import os
import tempfile  # noqa: F401 - retained as a patch target in download endpoint tests
from types import SimpleNamespace
from urllib.parse import quote

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse  # noqa: F401 - retained as a patch target in download endpoint tests
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.archive_download import extract_file_download, resolve_extracted_file_path
from app.core.borg import borg
from app.core.borg_router import BorgRouter
from app.core.security import (
    check_repo_access,
    get_current_download_user,
    get_current_user,
    require_repository_access_by_path,
)
from app.database.database import get_db
from app.database.models import AgentMachine, DeleteArchiveJob, Repository, User
from app.services.agent_artifact_relay import agent_artifact_relay
from app.services.agent_job_dispatcher import dispatch_agent_job_best_effort
from app.services.log_policy import get_log_save_policy, job_has_logs_by_policy
from app.services.repository_executor import (
    is_agent_executor,
    queue_agent_repository_operation_job,
    wait_for_agent_repository_operation_job,
)
from app.utils.borg_env import (
    cleanup_temp_key_file,
    get_standard_ssh_opts,
    setup_borg_env,
)
from app.utils.ssh_utils import (
    resolve_repo_ssh_key_file,
)  # Backward-compatible patch target for tests
from app.utils.datetime_utils import serialize_datetime

logger = structlog.get_logger()
router = APIRouter()


def _build_repo_env(repo: Repository, db: Session):
    temp_key_file = resolve_repo_ssh_key_file(repo, db)
    ssh_opts = get_standard_ssh_opts(include_key_path=temp_key_file)
    env = setup_borg_env(passphrase=repo.passphrase, ssh_opts=ssh_opts)
    return env, temp_key_file


def _write_agent_extracted_file(result: dict, *, temp_dir: str, file_path: str) -> dict:
    if not result.get("success"):
        return {
            "success": False,
            "stderr": result.get("stderr")
            or result.get("message")
            or "Agent archive extraction failed",
        }

    content_base64 = result.get("content_base64")
    if not isinstance(content_base64, str):
        return {
            "success": False,
            "stderr": "Agent archive extraction did not return file content",
        }

    try:
        content = base64.b64decode(content_base64, validate=True)
    except (binascii.Error, ValueError):
        return {
            "success": False,
            "stderr": "Agent archive extraction returned invalid file content",
        }

    extracted_file_path = resolve_extracted_file_path(temp_dir, file_path)
    extracted_parent = os.path.dirname(extracted_file_path)
    if extracted_parent:
        os.makedirs(extracted_parent, exist_ok=True)
    with open(extracted_file_path, "wb") as extracted_file:
        extracted_file.write(content)

    return {"success": True, "stderr": result.get("stderr", "")}


# Agents advertising this capability stream an extracted file to the server over
# HTTP instead of returning it base64-encoded in a WebSocket message, so the
# download can be proxied straight to the client at any size. Older agents
# without it keep using the base64 path below.
ARTIFACT_UPLOAD_CAPABILITY = "artifact.upload"

# Time the download waits for the agent's first byte (reach the remote repo,
# find the archive+file, spawn borg). Once bytes flow there is no total cap.
AGENT_ARTIFACT_FIRST_BYTE_TIMEOUT = 60.0
# Max gap between chunks before a stalled stream is abandoned.
AGENT_ARTIFACT_IDLE_TIMEOUT = 60.0


def _content_disposition_attachment(filename: str) -> str:
    """Build a safe `Content-Disposition` for a user-controlled filename.

    Escapes an ASCII fallback (dropping quotes/backslashes/control chars so the
    header can't be broken or injected) and adds an RFC 5987 `filename*` UTF-8
    variant so non-ASCII names survive.
    """
    ascii_name = filename.encode("ascii", "ignore").decode("ascii")
    ascii_name = "".join(
        ch for ch in ascii_name if ch.isprintable() and ch not in '"\\'
    ).strip()
    ascii_name = ascii_name or "download"
    utf8_name = quote(filename, safe="")
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{utf8_name}"


def _repo_bound_agent(repo: Repository, db: Session) -> AgentMachine | None:
    if not repo.agent_machine_id:
        return None
    return (
        db.query(AgentMachine).filter(AgentMachine.id == repo.agent_machine_id).first()
    )


async def _stream_agent_archive_file(
    db: Session, repo: Repository, archive: str, file_path: str
) -> StreamingResponse:
    """Proxy a single archived file from the agent straight to the client.

    The agent runs `borg extract --stdout` and streams it to
    POST /jobs/{id}/artifact; those chunks are relayed here without buffering.
    """
    agent_job = queue_agent_repository_operation_job(
        db,
        repo,
        job_kind="repository.extract_archive_file",
        operation={"archive": archive, "file_path": file_path, "delivery": "artifact"},
    )
    agent_artifact_relay.register(agent_job.id)
    try:
        await dispatch_agent_job_best_effort(
            db,
            agent_job,
            repository_id=repo.id,
            archive=archive,
            file_path=file_path,
        )
    except Exception:
        agent_artifact_relay.unregister(agent_job.id)
        raise

    stream = agent_artifact_relay.stream(
        agent_job.id,
        first_byte_timeout=AGENT_ARTIFACT_FIRST_BYTE_TIMEOUT,
        idle_timeout=AGENT_ARTIFACT_IDLE_TIMEOUT,
    )
    # Pull the first chunk here so a timeout/failure still yields a proper status
    # code, before StreamingResponse commits 200 + headers to the client.
    try:
        first_chunk = await stream.__anext__()
    except StopAsyncIteration:
        first_chunk = None  # empty file
    except TimeoutError as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail={"key": "backend.errors.agents.repositoryOperationTimeout"},
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "key": "backend.errors.agents.repositoryOperationFailed",
                "message": str(exc),
            },
        ) from exc

    async def body():
        if first_chunk is not None:
            yield first_chunk
        async for chunk in stream:
            yield chunk

    filename = os.path.basename(file_path) or "download"
    return StreamingResponse(
        body(),
        media_type="application/octet-stream",
        headers={"Content-Disposition": _content_disposition_attachment(filename)},
    )


@router.get("/list")
async def list_archives(
    repository: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List archives in a repository"""
    try:
        # Validate repository exists
        repo = require_repository_access_by_path(db, current_user, repository, "viewer")
        env, temp_key_file = _build_repo_env(repo, db)
        try:
            result = await borg.list_archives(
                repo.path,
                remote_path=repo.remote_path,
                passphrase=repo.passphrase,
                bypass_lock=repo.bypass_lock,
                env=env,
            )
        finally:
            cleanup_temp_key_file(temp_key_file)
        if not result["success"]:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to list archives: {result['stderr']}",
            )

        return {"archives": result["stdout"]}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to list archives", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"key": "backend.errors.archives.failedListArchives"},
        )


@router.get("/{archive_id}/info")
async def get_archive_info(
    repository: str,
    archive_id: str,
    include_files: bool = False,
    file_limit: int = 1000,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get detailed information about a specific archive including command line, metadata, and optionally file listing"""
    try:
        # Validate repository exists
        repo = require_repository_access_by_path(db, current_user, repository, "viewer")
        env, temp_key_file = _build_repo_env(repo, db)
        try:
            result = await borg.info_archive(
                repo.path,
                archive_id,
                remote_path=repo.remote_path,
                passphrase=repo.passphrase,
                bypass_lock=repo.bypass_lock,
                env=env,
            )
        finally:
            cleanup_temp_key_file(temp_key_file)
        if not result["success"]:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to get archive info: {result['stderr']}",
            )

        # Parse JSON output from Borg
        try:
            archive_data = json.loads(result["stdout"])

            # Extract archive information
            if "archives" in archive_data and len(archive_data["archives"]) > 0:
                archive_info = archive_data["archives"][0]
            else:
                archive_info = {}

            # Build enhanced response with all metadata
            enhanced_info = {
                "name": archive_info.get("name"),
                "id": archive_info.get("id"),
                "start": archive_info.get("start"),
                "end": archive_info.get("end"),
                "duration": archive_info.get("duration"),
                "stats": archive_info.get("stats", {}),
                # Creation metadata
                "command_line": archive_info.get("command_line", []),
                "hostname": archive_info.get("hostname"),
                "username": archive_info.get("username"),
                # Technical details
                "chunker_params": archive_info.get("chunker_params"),
                "limits": archive_info.get("limits", {}),
                "comment": archive_info.get("comment", ""),
                # Repository info
                "repository": archive_data.get("repository", {}),
                "encryption": archive_data.get("encryption", {}),
                "cache": archive_data.get("cache", {}),
            }

            # Optionally fetch file listing
            if include_files:
                env, temp_key_file = _build_repo_env(repo, db)
                try:
                    list_result = await borg.list_archive_contents(
                        repo.path,
                        archive_id,
                        remote_path=repo.remote_path,
                        passphrase=repo.passphrase,
                        bypass_lock=repo.bypass_lock,
                        env=env,
                    )
                finally:
                    cleanup_temp_key_file(temp_key_file)
                if list_result["success"]:
                    try:
                        # Parse JSON-lines output
                        files = []
                        for line in list_result["stdout"].strip().split("\n"):
                            if line and len(files) < file_limit:
                                try:
                                    file_obj = json.loads(line)
                                    files.append(
                                        {
                                            "path": file_obj.get("path"),
                                            "type": file_obj.get("type"),
                                            "mode": file_obj.get("mode"),
                                            "user": file_obj.get("user"),
                                            "group": file_obj.get("group"),
                                            "size": file_obj.get("size"),
                                            "mtime": file_obj.get("mtime"),
                                            "healthy": file_obj.get("healthy", True),
                                        }
                                    )
                                except json.JSONDecodeError:
                                    continue
                        enhanced_info["files"] = files
                        enhanced_info["file_count"] = len(files)
                    except Exception as e:
                        logger.warning("Failed to parse file listing", error=str(e))
                        enhanced_info["files"] = []
                        enhanced_info["file_count"] = 0
                else:
                    enhanced_info["files"] = []
                    enhanced_info["file_count"] = 0

            return {"info": enhanced_info}

        except json.JSONDecodeError:
            # Fallback to raw output if not JSON
            logger.warning("Archive info is not JSON, returning raw output")
            return {"info": result["stdout"]}

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get archive info", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"key": "backend.errors.archives.failedGetArchiveInfo"},
        )


@router.get("/{archive_id}/contents")
async def get_archive_contents(
    repository: str,
    archive_id: str,
    path: str = "",
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get contents of an archive"""
    try:
        # Validate repository exists
        repo = require_repository_access_by_path(db, current_user, repository, "viewer")
        env, temp_key_file = _build_repo_env(repo, db)
        try:
            result = await borg.list_archive_contents(
                repo.path,
                archive_id,
                path,
                remote_path=repo.remote_path,
                passphrase=repo.passphrase,
                bypass_lock=repo.bypass_lock,
                env=env,
            )
        finally:
            cleanup_temp_key_file(temp_key_file)
        if not result["success"]:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to get archive contents: {result['stderr']}",
            )

        return {"contents": result["stdout"]}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get archive contents", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"key": "backend.errors.archives.failedGetArchiveContents"},
        )


@router.delete("/{archive_id}")
async def delete_archive(
    repository: str,
    archive_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete an archive in the background (non-blocking)"""
    try:
        # Validate repository exists first
        repo = require_repository_access_by_path(
            db, current_user, repository, "operator"
        )
        # Check if there's already a running delete job for this archive
        running_job = (
            db.query(DeleteArchiveJob)
            .filter(
                DeleteArchiveJob.repository_id == repo.id,
                DeleteArchiveJob.archive_name == archive_id,
                DeleteArchiveJob.status == "running",
            )
            .first()
        )

        if running_job:
            raise HTTPException(
                status_code=409,
                detail={
                    "key": "backend.errors.archives.deleteAlreadyRunning",
                    "params": {"jobId": running_job.id},
                },
            )

        # Create delete job record
        delete_job = DeleteArchiveJob(
            repository_id=repo.id,
            repository_path=repo.path,
            archive_name=archive_id,
            status="pending",
        )
        db.add(delete_job)
        db.commit()
        db.refresh(delete_job)

        # Execute delete asynchronously (non-blocking)
        asyncio.create_task(
            BorgRouter(
                SimpleNamespace(id=repo.id, borg_version=repo.borg_version)
            ).delete_archive(delete_job.id, archive_id)
        )

        logger.info(
            "Delete archive job created",
            job_id=delete_job.id,
            repository_id=repo.id,
            archive=archive_id,
            user=current_user.username,
        )

        return {
            "job_id": delete_job.id,
            "status": "pending",
            "message": "backend.success.archives.deletionStarted",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to start delete archive job", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start archive deletion: {str(e)}",
        )


@router.get("/download")
async def download_file_from_archive(
    repository: str,
    archive: str,
    file_path: str,
    current_user: User = Depends(get_current_download_user),
    db: Session = Depends(get_db),
):
    """Extract and download a specific file from an archive"""
    try:
        repo = require_repository_access_by_path(
            db,
            current_user,
            repository,
            "viewer",
            detail_key="backend.errors.archives.repositoryNotFound",
        )

        # New agents stream the file straight through; older agents (and
        # server-side repos) fall through to the base64/local path below.
        if is_agent_executor(repo):
            agent = _repo_bound_agent(repo, db)
            if agent and ARTIFACT_UPLOAD_CAPABILITY in (agent.capabilities or []):
                return await _stream_agent_archive_file(db, repo, archive, file_path)

        async def extract(temp_dir: str):
            if is_agent_executor(repo):
                agent_job = queue_agent_repository_operation_job(
                    db,
                    repo,
                    job_kind="repository.extract_archive_file",
                    operation={"archive": archive, "file_path": file_path},
                )
                await dispatch_agent_job_best_effort(
                    db,
                    agent_job,
                    repository_id=repo.id,
                    archive=archive,
                    file_path=file_path,
                )
                result = await wait_for_agent_repository_operation_job(db, agent_job.id)
                return _write_agent_extracted_file(
                    result,
                    temp_dir=temp_dir,
                    file_path=file_path,
                )

            env, temp_key_file = _build_repo_env(repo, db)
            try:
                return await borg.extract_archive(
                    repo.path,
                    archive,
                    [file_path],
                    temp_dir,
                    dry_run=False,
                    remote_path=repo.remote_path,
                    passphrase=repo.passphrase,
                    bypass_lock=repo.bypass_lock,
                    env=env,
                )
            finally:
                cleanup_temp_key_file(temp_key_file)

        return await extract_file_download(
            file_path,
            extract,
            temp_dir_factory=tempfile.mkdtemp,
            path_exists=os.path.exists,
            file_response_factory=FileResponse,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Failed to download file from archive",
            repository=repository,
            archive=archive,
            file_path=file_path,
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to download file: {str(e)}",
        )


# Delete job status endpoints
@router.get("/delete-jobs/{job_id}")
async def get_delete_job_status(
    job_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get status of a delete archive job"""
    try:
        job = db.query(DeleteArchiveJob).filter(DeleteArchiveJob.id == job_id).first()
        if not job:
            raise HTTPException(
                status_code=404,
                detail={"key": "backend.errors.archives.deleteJobNotFound"},
            )
        repo = db.query(Repository).filter(Repository.id == job.repository_id).first()
        if repo:
            check_repo_access(db, current_user, repo, "viewer")

        has_logs = job_has_logs_by_policy(
            job,
            get_log_save_policy(db),
            output_text=[job.logs, job.error_message],
            file_path=job.log_file_path,
        )

        # Read log file only when the current policy allows this job's logs.
        logs = None
        if has_logs and job.log_file_path and os.path.exists(job.log_file_path):
            try:
                with open(job.log_file_path, "r") as f:
                    logs = f.read()
            except Exception as e:
                logger.warning("Failed to read delete log file", error=str(e))

        return {
            "id": job.id,
            "repository_id": job.repository_id,
            "archive_name": job.archive_name,
            "status": job.status,
            "started_at": serialize_datetime(job.started_at),
            "completed_at": serialize_datetime(job.completed_at),
            "progress": job.progress,
            "progress_message": job.progress_message,
            "error_message": job.error_message,
            "logs": logs,
            "has_logs": has_logs,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get delete job status", error=str(e), job_id=job_id)
        raise HTTPException(
            status_code=500, detail=f"Failed to get job status: {str(e)}"
        )


@router.post("/delete-jobs/{job_id}/cancel")
async def cancel_delete_job(
    job_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Cancel a running delete job"""
    try:
        job = db.query(DeleteArchiveJob).filter(DeleteArchiveJob.id == job_id).first()
        if not job:
            raise HTTPException(
                status_code=404,
                detail={"key": "backend.errors.archives.deleteJobNotFound"},
            )
        repo = db.query(Repository).filter(Repository.id == job.repository_id).first()
        if repo:
            check_repo_access(db, current_user, repo, "operator")
        await delete_archive_service.cancel_delete(job_id, db)
        return {"message": "backend.success.archives.deletionCancelled"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Failed to cancel delete job", error=str(e), job_id=job_id)
        raise HTTPException(
            status_code=500, detail=f"Failed to cancel delete job: {str(e)}"
        )
