from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
import os  # noqa: F401
import structlog

from app.database.models import User, Repository, SystemSettings, AgentJob
from app.database.database import get_db
from app.api.auth import get_current_user
from app.core.borg_router import BorgRouter
from app.services.agent_job_dispatcher import dispatch_agent_job_best_effort
from app.services.archive_browse_service import (
    add_managed_archive_metadata_to_items,
    build_browse_items,
    parse_archive_items,
)
from app.services.cache_service import archive_cache
from app.services.repository_executor import (
    get_agent_archive_browse_job,
    is_agent_executor,
    queue_agent_repository_operation_job,
    wait_for_agent_repository_operation_job,
)
from app.utils.borg_env import (
    get_standard_ssh_opts,
    setup_borg_env,
    cleanup_temp_key_file,
)
from app.utils.ssh_utils import (
    resolve_repo_ssh_key_file,
)  # Backward-compatible patch target for tests

logger = structlog.get_logger(__name__)

router = APIRouter()


def _drop_agent_job_result(db: Session, agent_job_id: int) -> None:
    """Clear a consumed browse listing from ``agent_jobs.result``.

    A ``list_archive_contents`` result holds the archive's full ``borg list``
    output and can be large. It only needs to survive until the polling browse
    request reads it once; the parsed items are cached afterwards and the agent
    can reproduce them on demand. Clearing it avoids keeping one copy per browse.
    """
    try:
        db.query(AgentJob).filter(AgentJob.id == agent_job_id).update(
            {AgentJob.result: None}, synchronize_session=False
        )
        db.commit()
    except Exception as exc:  # best-effort cleanup; never fail the browse on it
        db.rollback()
        logger.warning(
            "Failed to drop consumed agent browse job result",
            agent_job_id=agent_job_id,
            error=str(exc),
        )


# Memory safety limits
MAX_ITEMS_IN_MEMORY = 1_000_000  # Maximum number of items to load into memory
MAX_ESTIMATED_MEMORY_MB = 1024  # Maximum estimated memory usage (1GB)
ITEM_SIZE_ESTIMATE = 200  # Average bytes per item in memory (conservative estimate)


def _build_repo_env(repo: Repository, db: Session):
    temp_key_file = resolve_repo_ssh_key_file(repo, db)
    ssh_opts = get_standard_ssh_opts(include_key_path=temp_key_file)
    env = setup_borg_env(passphrase=repo.passphrase, ssh_opts=ssh_opts)
    return env, temp_key_file


def _get_browse_result_cache_key(archive_name: str, path: str) -> str:
    normalized_path = path.strip("/")
    if not normalized_path:
        return f"{archive_name}::browse-managed-root"
    return f"{archive_name}::browse-managed::{normalized_path}"


def _is_browse_result_payload(items) -> bool:
    return isinstance(items, list) and all(
        isinstance(item, dict) and "name" in item and "path" in item for item in items
    )


# How long a single browse request waits for the agent's list_archive_contents
# job before returning HTTP 202 so the client polls. Large managed archives
# (hundreds of thousands of entries) can take longer than any single request
# should block; small ones still resolve within this first window.
BROWSE_AGENT_WAIT_SECONDS = 8


async def _run_or_poll_agent_browse(
    db: Session,
    repository: Repository,
    *,
    archive_name: str,
    max_items: int,
    job_id: Optional[int],
) -> tuple[Optional[dict], int]:
    """Queue (``job_id`` is None) or resume (``job_id`` given) the agent's archive
    listing job and wait a bounded window for it.

    Returns ``(result, job_id)``. ``result`` is the completed job payload, or
    ``None`` when the job is still running — the caller then returns HTTP 202 with
    the job id so the client polls. The completed listing is parsed and cached by
    the caller, so subsequent opens of the same archive are served from cache.
    """
    if job_id is None:
        agent_job = queue_agent_repository_operation_job(
            db,
            repository,
            job_kind="repository.list_archive_contents",
            operation={"archive": archive_name, "path": "", "max_lines": max_items},
        )
        await dispatch_agent_job_best_effort(
            db,
            agent_job,
            repository_id=repository.id,
            archive_name=archive_name,
        )
        job_id = agent_job.id
    elif get_agent_archive_browse_job(db, repository, job_id, archive_name) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"key": "backend.errors.agents.jobNotFound"},
        )

    try:
        result = await wait_for_agent_repository_operation_job(
            db, job_id, timeout_seconds=BROWSE_AGENT_WAIT_SECONDS
        )
    except HTTPException as exc:
        if exc.status_code == status.HTTP_504_GATEWAY_TIMEOUT:
            return None, job_id
        raise
    return result, job_id


async def _list_archive_contents_local(
    db: Session,
    repository: Repository,
    *,
    archive_name: str,
    max_items: int,
) -> dict:
    env, temp_key_file = _build_repo_env(repository, db)
    try:
        return await BorgRouter(repository).list_archive_contents(
            archive=archive_name,
            path="",  # Always fetch all items
            max_lines=max_items,  # Kill borg process if this limit is exceeded
            env=env,
        )
    finally:
        cleanup_temp_key_file(temp_key_file)


@router.get("/{repository_id}/{archive_name}")
async def browse_archive_contents(
    repository_id: int,
    archive_name: str,
    path: str = Query("", description="Path within archive to browse"),
    job_id: Optional[int] = Query(
        None,
        description="Poll an in-flight agent browse job queued by a prior call",
    ),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Browse contents of an archive at a specific path (directory-by-directory)"""
    # Job id whose result should be cleared in `finally`, set only once a
    # completed agent listing has been consumed (None for local repos / pending).
    consumed_browse_job_id: Optional[int] = None
    try:
        repository = db.query(Repository).filter(Repository.id == repository_id).first()
        if not repository:
            raise HTTPException(
                status_code=404,
                detail={"key": "backend.errors.restore.repositoryNotFound"},
            )

        # Get memory limit settings from database
        settings = db.query(SystemSettings).first()
        max_items = (
            settings.browse_max_items
            if settings and settings.browse_max_items
            else MAX_ITEMS_IN_MEMORY
        )
        max_memory_mb = (
            settings.browse_max_memory_mb
            if settings and settings.browse_max_memory_mb
            else MAX_ESTIMATED_MEMORY_MB
        )

        # Check cache first
        result_cache_key = _get_browse_result_cache_key(archive_name, path)
        cached_result = await archive_cache.get(repository_id, result_cache_key)
        if cached_result is not None and _is_browse_result_payload(cached_result):
            cached_result = add_managed_archive_metadata_to_items(cached_result)
            logger.info(
                "Using cached archive browse result",
                archive=archive_name,
                path=path,
                items_count=len(cached_result),
            )
            return {"items": cached_result}

        all_items = await archive_cache.get(repository_id, archive_name)

        if all_items is not None:
            logger.info(
                "Using cached archive contents",
                archive=archive_name,
                items_count=len(all_items),
            )
        else:
            # If not in cache, fetch from borg with streaming (prevents OOM)
            # Pass max_items as max_lines to ensure borg process is killed if limit exceeded
            if is_agent_executor(repository):
                # Agent listings run remotely and can be slow; queue/poll a job
                # instead of blocking the request until it finishes or times out.
                result, browse_job_id = await _run_or_poll_agent_browse(
                    db,
                    repository,
                    archive_name=archive_name,
                    max_items=max_items,
                    job_id=job_id,
                )
                if result is None:
                    # Still running — client polls with this id; not consumed yet.
                    return JSONResponse(
                        status_code=status.HTTP_202_ACCEPTED,
                        content={"status": "pending", "jobId": browse_job_id},
                    )
                consumed_browse_job_id = browse_job_id
            else:
                result = await _list_archive_contents_local(
                    db,
                    repository,
                    archive_name=archive_name,
                    max_items=max_items,
                )

            # Check if line limit was exceeded (borg process was killed to prevent OOM)
            if result.get("line_count_exceeded"):
                lines_read = result.get("lines_read", 0)
                logger.error(
                    "Archive too large for safe browsing - terminated early",
                    archive=archive_name,
                    lines_read=lines_read,
                    max_allowed=max_items,
                )
                raise HTTPException(
                    status_code=413,
                    detail={
                        "key": "backend.errors.browse.archiveTooLarge",
                        "params": {"linesRead": lines_read, "maxItems": max_items},
                    },
                )

            # Parse all items
            all_items = []
            if result.get("stdout"):
                lines = result["stdout"].strip().split("\n")
                total_lines = len(lines)

                # Memory safety check: Estimate memory usage
                estimated_memory_mb = (total_lines * ITEM_SIZE_ESTIMATE) / (1024 * 1024)

                logger.info(
                    "Fetching archive contents",
                    archive=archive_name,
                    total_lines=total_lines,
                    estimated_memory_mb=round(estimated_memory_mb, 2),
                )

                # Secondary check: Verify memory estimate is within bounds
                # (This should rarely trigger now that streaming enforces line limits)
                if estimated_memory_mb > max_memory_mb:
                    logger.error(
                        "Estimated memory usage too high",
                        archive=archive_name,
                        estimated_memory_mb=round(estimated_memory_mb, 2),
                        max_allowed_mb=max_memory_mb,
                    )
                    raise HTTPException(
                        status_code=413,
                        detail={
                            "key": "backend.errors.browse.archiveMemoryTooHigh",
                            "params": {
                                "estimatedMb": round(estimated_memory_mb),
                                "maxMb": max_memory_mb,
                            },
                        },
                    )

                all_items = parse_archive_items(result["stdout"])

                # Store in cache (cache service will enforce its own size limits)
                cache_success = await archive_cache.set(
                    repository_id, archive_name, all_items
                )
                if cache_success:
                    logger.info(
                        "Cached archive contents",
                        archive=archive_name,
                        items_count=len(all_items),
                    )
                else:
                    logger.warning(
                        "Failed to cache archive (too large or cache full)",
                        archive=archive_name,
                        items_count=len(all_items),
                    )

        items = build_browse_items(all_items, path)

        logger.info(
            "Archive contents parsed for browsing",
            archive=archive_name,
            path=path,
            items_count=len(items),
            first_few_items=[item["name"] for item in items[:10]],
            directory_sizes=[
                (item["name"], item.get("size"))
                for item in items[:5]
                if item["type"] == "directory"
            ],
        )

        await archive_cache.set(repository_id, result_cache_key, items)

        return {"items": items}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Failed to browse archive contents",
            repository_id=repository_id,
            archive_name=archive_name,
            path=path,
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to browse archive: {str(e)}",
        )
    finally:
        if consumed_browse_job_id is not None:
            _drop_agent_job_result(db, consumed_browse_job_id)
