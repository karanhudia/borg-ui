from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
import structlog

from app.database.models import User, Repository, SystemSettings
from app.database.database import get_db
from app.api.auth import get_current_user
from app.core.borg_router import BorgRouter
from app.services.archive_browse_service import build_browse_items, parse_archive_items
from app.services.cache_service import archive_cache
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
        return f"{archive_name}::browse-root"
    return f"{archive_name}::browse::{normalized_path}"


def _is_browse_result_payload(items) -> bool:
    return isinstance(items, list) and all(
        isinstance(item, dict) and "name" in item and "path" in item for item in items
    )


@router.get("/{repository_id}/{archive_name}")
async def browse_archive_contents(
    repository_id: int,
    archive_name: str,
    path: str = Query("", description="Path within archive to browse"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Browse contents of an archive at a specific path (directory-by-directory)"""
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
            env, temp_key_file = _build_repo_env(repository, db)
            try:
                result = await BorgRouter(repository).list_archive_contents(
                    archive=archive_name,
                    path="",  # Always fetch all items
                    max_lines=max_items,  # Kill borg process if this limit is exceeded
                    env=env,
                )
            finally:
                cleanup_temp_key_file(temp_key_file)

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
