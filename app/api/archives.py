import asyncio
import base64
import binascii
import json
import os
import re
import tempfile  # noqa: F401 - retained as a patch target in download endpoint tests
from urllib.parse import quote

import structlog
from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import FileResponse  # noqa: F401 - retained as a patch target in download endpoint tests
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.archive_download import extract_file_download, resolve_extracted_file_path
from app.core.borg import borg
from app.core.borg2 import normalize_repo_info_encryption
from app.core.security import (
    check_repo_access,
    get_current_download_user,
    get_current_user,
    require_repository_access_by_path,
)
from app.database.database import get_db
from app.database.models import AgentMachine, Repository, User
from app.services.agent_artifact_relay import agent_artifact_relay
from app.services.agent_job_dispatcher import (
    dispatch_agent_cancel_if_connected,
    dispatch_agent_job_best_effort,
)
from app.services.log_policy import get_log_save_policy, job_has_logs_by_policy
from app.services.operations.enqueue import enqueue
from app.services.operations.job_facade import resolve_maintenance_job
from app.services.operations.maintenance_start import active_delete_for_archive
from app.services.repository_executor import (
    abandon_agent_repository_operation_job,
    agent_operation_failed_detail,
    agent_timezone_for_repository,
    cancel_unclaimed_agent_repository_job,
    is_agent_executor,
    queue_agent_repository_operation_job,
    wait_for_agent_repository_operation_job,
)
from app.utils.borg_env import (
    cleanup_temp_key_file,
    effective_repository_remote_path,
    get_standard_ssh_opts,
    REQUEST_LOCK_WAIT,
    setup_borg_env,
)
from app.utils.ssh_utils import (
    resolve_repo_ssh_key_file,  # noqa: F401
    resolve_repository_ssh_connection,
)  # Backward-compatible patch target for tests
from app.utils.datetime_utils import serialize_borg_archive_time, serialize_datetime
from app.utils.borg_arguments import validate_operand

logger = structlog.get_logger()
router = APIRouter()


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
    if remote_path := effective_repository_remote_path(repo):
        env["BORG_REMOTE_PATH"] = remote_path
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
# How long taking a streamed download's job back waits for its cancel to be
# sent to the agent; the send itself goes on.
AGENT_CANCEL_SEND_TIMEOUT = 5.0
# Strong references: the loop only holds weak ones, and a cancel send that
# outlives its download must still reach the agent.
_CANCEL_SEND_TASKS: set[asyncio.Task] = set()


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


_ARCHIVE_ID_RE = re.compile(r"^[0-9a-fA-F]{16,}$")


def _archive_extract_selector(archive: str, repo: Repository) -> str:
    """Address a Borg 2 archive by id via the `aid:` selector.

    The frontend sends the archive id (hex) for Borg 2, but a bare id is
    interpreted by borg as an archive NAME → no match → an empty (0-byte)
    extract for an archive series. Borg 1 names are unique and passed as-is.
    """
    if not archive or getattr(repo, "borg_version", 1) != 2:
        return archive
    if archive.startswith("aid:"):
        return archive
    return f"aid:{archive}" if _ARCHIVE_ID_RE.fullmatch(archive) else archive


async def agent_file_download(
    db: Session, repo: Repository, archive: str, file_path: str
):
    """Download one file of an agent repository's archive, extracted on the
    agent. `archive` is the exact selector (`aid:<hex>` for Borg 2).

    New agents stream the file straight through; older agents return it
    base64-encoded in their job result."""
    agent = _repo_bound_agent(repo, db)
    if agent and ARTIFACT_UPLOAD_CAPABILITY in (agent.capabilities or []):
        return await _stream_agent_archive_file(db, repo, archive, file_path)

    async def extract(temp_dir: str):
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
        try:
            result = await wait_for_agent_repository_operation_job(db, agent_job.id)
        except HTTPException as exc:
            if exc.status_code == status.HTTP_504_GATEWAY_TIMEOUT:
                # nobody waits for the file any more: take the job back
                abandoned = abandon_agent_repository_operation_job(db, agent_job.id)
                if abandoned is not None and abandoned.status == "cancel_requested":
                    await dispatch_agent_cancel_if_connected(abandoned)
            raise
        return _write_agent_extracted_file(
            result,
            temp_dir=temp_dir,
            file_path=file_path,
        )

    return await extract_file_download(
        file_path,
        extract,
        temp_dir_factory=tempfile.mkdtemp,
        path_exists=os.path.exists,
        file_response_factory=FileResponse,
    )


class _AgentDownloadResponse(StreamingResponse):
    """A streamed agent download that closes its body when the response
    ends: Starlette leaves a body it stopped reading (a client that went
    away) suspended, and the body's cleanup takes the agent job back."""

    async def __call__(self, scope, receive, send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            await self.body_iterator.aclose()


async def _take_back_streamed_agent_job(db: Session, agent_job_id: int) -> None:
    """End a streamed download's agent job that nobody reads any more: an
    unclaimed job is cancelled, a running one is asked to stop."""
    abandoned = abandon_agent_repository_operation_job(db, agent_job_id)
    agent_artifact_relay.unregister(agent_job_id)
    if abandoned is not None and abandoned.status == "cancel_requested":
        # Shielded: a download ended by its client's disconnect is being
        # cancelled itself, and the agent must still hear of it. Bounded: a
        # send queued behind a stalled one goes on without holding the answer.
        send = asyncio.ensure_future(dispatch_agent_cancel_if_connected(abandoned))
        _CANCEL_SEND_TASKS.add(send)
        send.add_done_callback(_CANCEL_SEND_TASKS.discard)
        try:
            await asyncio.wait_for(
                asyncio.shield(send), timeout=AGENT_CANCEL_SEND_TIMEOUT
            )
        except TimeoutError:
            logger.warning(
                "Cancel of a streamed download's agent job still sending",
                agent_job_id=agent_job_id,
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
    except asyncio.CancelledError:
        # the request ended while the job was being handed over
        await _take_back_streamed_agent_job(db, agent_job.id)
        raise
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
    except asyncio.CancelledError:
        # the request itself ended (a shutdown, a dropped connection)
        await _take_back_streamed_agent_job(db, agent_job.id)
        raise
    except TimeoutError as exc:
        await _take_back_streamed_agent_job(db, agent_job.id)
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail={"key": "backend.errors.agents.repositoryOperationTimeout"},
        ) from exc
    except RuntimeError as exc:
        await _take_back_streamed_agent_job(db, agent_job.id)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=agent_operation_failed_detail(str(exc)),
        ) from exc

    async def body():
        delivered = False
        try:
            if first_chunk is not None:
                yield first_chunk
            async for chunk in stream:
                yield chunk
            delivered = True
        finally:
            # After the end of the stream the agent reports its completion;
            # a cancel then would turn a delivered download into a failure.
            if not delivered:
                await _take_back_streamed_agent_job(db, agent_job.id)

    filename = os.path.basename(file_path) or "download"
    return _AgentDownloadResponse(
        body(),
        media_type="application/octet-stream",
        headers={"Content-Disposition": _content_disposition_attachment(filename)},
    )


def _tar_strip_components(directory_path: str) -> int:
    """Keep the selected directory as the root of its downloaded tar file."""
    return max(0, len([part for part in directory_path.split("/") if part]) - 1)


async def _stream_agent_archive_tar(
    db: Session, repo: Repository, archive: str, directory_path: str
) -> StreamingResponse:
    """Proxy a tar export from an agent without buffering it on either side."""
    agent_job = queue_agent_repository_operation_job(
        db,
        repo,
        job_kind="repository.export_archive_tar",
        operation={
            "archive": archive,
            "directory_path": directory_path,
            "strip_components": _tar_strip_components(directory_path),
            "delivery": "artifact",
        },
    )
    agent_artifact_relay.register(agent_job.id)
    try:
        await dispatch_agent_job_best_effort(
            db,
            agent_job,
            repository_id=repo.id,
            archive=archive,
            directory_path=directory_path,
        )
    except asyncio.CancelledError:
        # the request ended while the job was being handed over
        await _take_back_streamed_agent_job(db, agent_job.id)
        raise
    except Exception:
        agent_artifact_relay.unregister(agent_job.id)
        raise

    stream = agent_artifact_relay.stream(
        agent_job.id,
        first_byte_timeout=AGENT_ARTIFACT_FIRST_BYTE_TIMEOUT,
        idle_timeout=AGENT_ARTIFACT_IDLE_TIMEOUT,
    )
    try:
        first_chunk = await stream.__anext__()
    except StopAsyncIteration:
        first_chunk = None
    except asyncio.CancelledError:
        # the request itself ended (a shutdown, a dropped connection)
        await _take_back_streamed_agent_job(db, agent_job.id)
        raise
    except TimeoutError as exc:
        await _take_back_streamed_agent_job(db, agent_job.id)
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail={"key": "backend.errors.agents.repositoryOperationTimeout"},
        ) from exc
    except RuntimeError as exc:
        await _take_back_streamed_agent_job(db, agent_job.id)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=agent_operation_failed_detail(str(exc)),
        ) from exc

    async def body():
        delivered = False
        try:
            if first_chunk is not None:
                yield first_chunk
            async for chunk in stream:
                yield chunk
            delivered = True
        finally:
            # After the end of the stream the agent reports its completion;
            # a cancel then would turn a delivered download into a failure.
            if not delivered:
                await _take_back_streamed_agent_job(db, agent_job.id)

    filename = f"{os.path.basename(directory_path.rstrip('/')) or 'archive'}.tar"
    return _AgentDownloadResponse(
        body(),
        media_type="application/x-tar",
        headers={"Content-Disposition": _content_disposition_attachment(filename)},
    )


async def _stream_server_archive_tar(
    repo: Repository, archive: str, directory_path: str, db: Session
) -> StreamingResponse:
    """Start a Borg tar export and verify its first bytes before returning 200."""
    env, temp_key_file = _build_repo_env(repo, db)
    try:
        stream = borg.export_archive_tar(
            repo.path,
            archive,
            directory_path,
            remote_path=effective_repository_remote_path(repo),
            passphrase=repo.passphrase,
            bypass_lock=repo.bypass_lock,
            env=env,
            strip_components=_tar_strip_components(directory_path),
        )
        iterator = stream.__aiter__()
        try:
            first_chunk = await anext(iterator)
        except StopAsyncIteration:
            if stream.return_code not in (None, 0):
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Failed to download folder: {stream.stderr or 'Borg export failed'}",
                )
            first_chunk = None
    except Exception:
        cleanup_temp_key_file(temp_key_file)
        raise

    async def body():
        try:
            if first_chunk is not None:
                yield first_chunk
            async for chunk in iterator:
                yield chunk
        finally:
            await stream.close()
            cleanup_temp_key_file(temp_key_file)

    filename = f"{os.path.basename(directory_path.rstrip('/')) or 'archive'}.tar"
    return StreamingResponse(
        body(),
        media_type="application/x-tar",
        headers={"Content-Disposition": _content_disposition_attachment(filename)},
    )


async def _agent_read_result(
    db: Session,
    repo: Repository,
    job_kind: str,
    *,
    operation: dict | None = None,
    timeout_key: str,
) -> dict:
    """Run a read job of an agent repository on its agent and return the
    result: the deprecated routes' agent path (#1393)."""
    from app.api.repositories import get_operation_timeouts

    agent_job = queue_agent_repository_operation_job(
        db, repo, job_kind=job_kind, operation=operation
    )
    await dispatch_agent_job_best_effort(db, agent_job, repository_id=repo.id)
    try:
        return await wait_for_agent_repository_operation_job(
            db, agent_job.id, timeout_seconds=get_operation_timeouts(db)[timeout_key]
        )
    except HTTPException as exc:
        if exc.status_code == status.HTTP_504_GATEWAY_TIMEOUT:
            # Left queued (the agent was not connected to take it), the job
            # would count as the repository's active work until the agent
            # comes back; one the agent claimed runs to its end.
            cancel_unclaimed_agent_repository_job(db, agent_job.id)
        raise


def _read_succeeded(result: dict) -> bool:
    """A server result says `success`; an agent result carries Borg's
    return code."""
    return (
        result.get("success", True) is not False and result.get("return_code", 0) == 0
    )


@router.get("/list")
async def list_archives(
    repository: str,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List archives in a repository"""
    try:
        # Validate repository exists
        repo = require_repository_access_by_path(db, current_user, repository, "viewer")
        if is_agent_executor(repo):
            result = await _agent_read_result(
                db, repo, "repository.list_archives", timeout_key="list_timeout"
            )
        else:
            env, temp_key_file = _build_repo_env(repo, db)
            try:
                result = await borg.list_archives(
                    repo.path,
                    remote_path=effective_repository_remote_path(repo),
                    passphrase=repo.passphrase,
                    bypass_lock=repo.bypass_lock,
                    env=env,
                )
            finally:
                cleanup_temp_key_file(temp_key_file)
        if not _read_succeeded(result):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to list archives: {result.get('stderr', '')}",
            )

        response.headers["Deprecation"] = "true"
        response.headers["Link"] = (
            f'</api/repositories/{repo.id}/archives>; rel="successor-version"'
        )
        return {"archives": result.get("stdout", "")}
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
        validate_operand(archive_id, "archive selector")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    try:
        # Validate repository exists
        repo = require_repository_access_by_path(db, current_user, repository, "viewer")
        agent = is_agent_executor(repo)
        if agent:
            archive_id = _archive_extract_selector(archive_id, repo)
            result = await _agent_read_result(
                db,
                repo,
                "repository.archive_info",
                operation={"archive": archive_id},
                timeout_key="info_timeout",
            )
        else:
            env, temp_key_file = _build_repo_env(repo, db)
            try:
                result = await borg.info_archive(
                    repo.path,
                    archive_id,
                    remote_path=effective_repository_remote_path(repo),
                    passphrase=repo.passphrase,
                    bypass_lock=repo.bypass_lock,
                    env=env,
                )
            finally:
                cleanup_temp_key_file(temp_key_file)
        # An agent renders Borg's times in its own zone; the server's
        # wrapper runs under TZ=UTC.
        time_zone = agent_timezone_for_repository(db, repo) if agent else "UTC"
        if not _read_succeeded(result):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to get archive info: {result.get('stderr', '')}",
            )

        # Parse JSON output from Borg
        try:
            archive_data = json.loads(result.get("stdout") or "")

            # Extract archive information
            if "archives" in archive_data and len(archive_data["archives"]) > 0:
                archive_info = archive_data["archives"][0]
            else:
                archive_info = {}

            # Build enhanced response with all metadata
            enhanced_info = {
                "name": archive_info.get("name"),
                "id": archive_info.get("id"),
                # Re-rendered with an explicit offset so the frontend does
                # not read the value as local time.
                "start": serialize_borg_archive_time(
                    archive_info.get("start"), timezone_name=time_zone
                ),
                "end": serialize_borg_archive_time(
                    archive_info.get("end"), timezone_name=time_zone
                ),
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
                "encryption": normalize_repo_info_encryption(archive_data).get(
                    "encryption", {}
                ),
                "cache": archive_data.get("cache", {}),
            }

            # Optionally fetch file listing
            if include_files:
                if agent:
                    try:
                        list_result = await _agent_read_result(
                            db,
                            repo,
                            "repository.list_archive_contents",
                            # No line cap: the agent ends a listing at its
                            # cap with a failure. `file_limit` cuts it below,
                            # as on the server.
                            operation={"archive": archive_id, "path": ""},
                            timeout_key="list_timeout",
                        )
                    except HTTPException as exc:
                        # the files are best effort, as on the server: the
                        # archive info stands without them
                        logger.warning(
                            "Agent file listing for archive info failed",
                            repository_id=repo.id,
                            archive=archive_id,
                            status_code=exc.status_code,
                        )
                        list_result = {"success": False}
                else:
                    env, temp_key_file = _build_repo_env(repo, db)
                    try:
                        list_result = await borg.list_archive_contents(
                            repo.path,
                            archive_id,
                            remote_path=effective_repository_remote_path(repo),
                            passphrase=repo.passphrase,
                            bypass_lock=repo.bypass_lock,
                            env=env,
                        )
                    finally:
                        cleanup_temp_key_file(temp_key_file)
                if _read_succeeded(list_result):
                    try:
                        # Parse JSON-lines output
                        files = []
                        for line in (
                            (list_result.get("stdout") or "").strip().split("\n")
                        ):
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
                                            # Re-rendered with an explicit
                                            # offset, as the times above.
                                            "mtime": serialize_borg_archive_time(
                                                file_obj.get("mtime"),
                                                timezone_name=time_zone,
                                            ),
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
            return {"info": result.get("stdout", "")}

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
        validate_operand(archive_id, "archive selector")
        if path:
            validate_operand(path, "archive path", archive_path=True)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    try:
        # Validate repository exists
        repo = require_repository_access_by_path(db, current_user, repository, "viewer")
        if is_agent_executor(repo):
            result = await _agent_read_result(
                db,
                repo,
                "repository.list_archive_contents",
                operation={
                    "archive": _archive_extract_selector(archive_id, repo),
                    "path": path,
                },
                timeout_key="list_timeout",
            )
        else:
            env, temp_key_file = _build_repo_env(repo, db)
            try:
                result = await borg.list_archive_contents(
                    repo.path,
                    archive_id,
                    path,
                    remote_path=effective_repository_remote_path(repo),
                    passphrase=repo.passphrase,
                    bypass_lock=repo.bypass_lock,
                    env=env,
                )
            finally:
                cleanup_temp_key_file(temp_key_file)
        if not _read_succeeded(result):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to get archive contents: {result.get('stderr', '')}",
            )

        return {"contents": result.get("stdout", "")}
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
        validate_operand(archive_id, "archive selector")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    try:
        # Validate repository exists first
        repo = require_repository_access_by_path(
            db, current_user, repository, "operator"
        )
        # Borg 2: address the archive by id (aid:) so a series delete removes
        # exactly one archive; a bare series name matches N → borg errors. The
        # frontend sends the archive id for Borg 2; Borg 1 names are unique.
        archive_id = _archive_extract_selector(archive_id, repo)
        # Check if there's already a running delete job for this archive.
        # Deletes are rejected per archive, not per repository (spec section
        # 13 phase 5): two different archives may be removed at once, the
        # same one may not.
        running_job = active_delete_for_archive(db, repo.id, archive_id)
        if running_job:
            raise HTTPException(
                status_code=409,
                detail={
                    "key": "backend.errors.archives.deleteAlreadyRunning",
                    "params": {"jobId": running_job.id},
                },
            )

        delete_job = enqueue(
            db,
            "delete_archive",
            repository_id=repo.id,
            trigger="manual",
            params={"archive_name": archive_id},
            triggered_by_user_id=current_user.id,
        )

        logger.info(
            "Delete archive operation queued",
            operation_id=delete_job.id,
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
        validate_operand(archive, "archive selector")
        if file_path:
            validate_operand(file_path, "archive path", archive_path=True)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    try:
        repo = require_repository_access_by_path(
            db,
            current_user,
            repository,
            "viewer",
            detail_key="backend.errors.archives.repositoryNotFound",
        )

        # Borg 2: address the archive by id (aid:) so extract targets exactly one
        # archive in a series; a bare id would be read as a name → 0-byte file.
        archive = _archive_extract_selector(archive, repo)

        if is_agent_executor(repo):
            return await agent_file_download(db, repo, archive, file_path)

        async def extract(temp_dir: str):
            env, temp_key_file = _build_repo_env(repo, db)
            try:
                return await borg.extract_archive(
                    repo.path,
                    archive,
                    [file_path],
                    temp_dir,
                    dry_run=False,
                    remote_path=effective_repository_remote_path(repo),
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


@router.get("/download-folder")
async def download_folder_from_archive(
    repository: str,
    archive: str,
    directory_path: str,
    current_user: User = Depends(get_current_download_user),
    db: Session = Depends(get_db),
):
    """Download one archived directory as a streaming tar file."""
    try:
        validate_operand(archive, "archive selector")
        if directory_path:
            validate_operand(directory_path, "archive path", archive_path=True)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not directory_path.strip().strip("/"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="directory_path is required",
        )
    try:
        repo = require_repository_access_by_path(
            db,
            current_user,
            repository,
            "viewer",
            detail_key="backend.errors.archives.repositoryNotFound",
        )
        archive = _archive_extract_selector(archive, repo)
        if is_agent_executor(repo):
            return await _stream_agent_archive_tar(db, repo, archive, directory_path)
        return await _stream_server_archive_tar(repo, archive, directory_path, db)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Failed to download folder from archive",
            repository=repository,
            archive=archive,
            directory_path=directory_path,
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to download folder: {str(e)}",
        )


# Delete job status endpoints
@router.get("/delete-jobs/{job_id}")
def get_delete_job_status(
    job_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get status of a delete archive job"""
    try:
        job = resolve_maintenance_job(db, job_id, "delete_archive")
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
        job = resolve_maintenance_job(db, job_id, "delete_archive")
        if job is None:
            raise HTTPException(
                status_code=404,
                detail={"key": "backend.errors.archives.deleteJobNotFound"},
            )
        repo = db.query(Repository).filter(Repository.id == job.repository_id).first()
        if repo:
            check_repo_access(db, current_user, repo, "operator")
        # The runner owns the kill and writes the terminal status (spec 7.7).
        from app.services.operations.runner import operation_runner

        await operation_runner.request_cancel(job_id)
        return {"message": "backend.success.archives.deletionCancelled"}
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Failed to cancel delete job", error=str(e), job_id=job_id)
        raise HTTPException(
            status_code=500, detail=f"Failed to cancel delete job: {str(e)}"
        )
