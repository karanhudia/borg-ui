from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
import structlog
import json
import hashlib
from datetime import datetime, timedelta

from app.database.models import User, Repository
from app.database.database import get_db
from app.api.auth import get_current_user
from app.core.borg import borg
from app.core.repository_locks import with_repository_lock

logger = structlog.get_logger(__name__)

router = APIRouter()

# In-memory cache for borg list results
# Key: (repository_id, archive_name)
# Value: {"data": list_of_items, "timestamp": datetime}
_archive_cache = {}
CACHE_TTL_SECONDS = 300  # 5 minutes

@router.get("/{repository_id}/{archive_name}")
@with_repository_lock('repository_id')
async def browse_archive_contents(
    repository_id: int,
    archive_name: str,
    path: str = Query("", description="Path within archive to browse"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Browse contents of an archive at a specific path (directory-by-directory)"""
    try:
        repository = db.query(Repository).filter(Repository.id == repository_id).first()
        if not repository:
            raise HTTPException(status_code=404, detail="Repository not found")

        # Check cache first
        cache_key = (repository_id, archive_name)
        now = datetime.utcnow()

        if cache_key in _archive_cache:
            cache_entry = _archive_cache[cache_key]
            cache_age = (now - cache_entry["timestamp"]).total_seconds()
            if cache_age < CACHE_TTL_SECONDS:
                logger.info("Using cached archive contents",
                           archive=archive_name,
                           cache_age_seconds=int(cache_age))
                all_items = cache_entry["data"]
            else:
                # Cache expired, remove it
                del _archive_cache[cache_key]
                all_items = None
        else:
            all_items = None

        # If not in cache or expired, fetch from borg
        if all_items is None:
            result = await borg.list_archive_contents(
                repository.path,
                archive_name,
                path="",  # Always fetch all items
                remote_path=repository.remote_path,
                passphrase=repository.passphrase
            )

            # Parse and cache all items
            all_items = []
            if result.get("stdout"):
                lines = result["stdout"].strip().split("\n")
                logger.info("Fetching and caching archive contents",
                           archive=archive_name,
                           total_lines=len(lines))

                for line in lines:
                    if line:
                        try:
                            item_data = json.loads(line)
                            item_path = item_data.get("path", "")
                            if item_path:
                                all_items.append({
                                    "path": item_path,
                                    "type": item_data.get("type", ""),
                                    "size": item_data.get("size")
                                })
                        except json.JSONDecodeError:
                            continue

                # Store in cache
                _archive_cache[cache_key] = {
                    "data": all_items,
                    "timestamp": now
                }
                logger.info("Cached archive contents",
                           archive=archive_name,
                           items_count=len(all_items))

        # Now filter the cached items for the requested path
        items = []
        seen_paths = set()

        for item in all_items:
            item_path = item["path"]
            item_type = item["type"]
            item_size = item.get("size")

            # Get relative path from current directory
            if path:
                # If we're in a subdirectory, only show items under that path
                if item_path.startswith(path + "/"):
                    relative_path = item_path[len(path) + 1:]
                elif item_path == path:
                    # Skip the directory itself
                    continue
                else:
                    # Item is not in this directory, skip it
                    continue
            else:
                # Root level - show everything
                relative_path = item_path

            # Strip leading slash for proper path handling
            relative_path = relative_path.lstrip("/")

            # Skip if empty after stripping
            if not relative_path:
                continue

            # Only show immediate children
            if "/" in relative_path:
                # This is a nested item, show only the directory
                dir_name = relative_path.split("/")[0]
                if dir_name not in seen_paths:
                    seen_paths.add(dir_name)
                    items.append({
                        "name": dir_name,
                        "type": "directory",
                        "path": f"{path}/{dir_name}" if path else dir_name
                    })
            else:
                # This is an immediate child
                if relative_path not in seen_paths:
                    seen_paths.add(relative_path)
                    items.append({
                        "name": relative_path,
                        "type": "directory" if item_type == "d" else "file",
                        "size": item_size,
                        "path": f"{path}/{relative_path}" if path else relative_path
                    })

        # Sort: directories first, then by name
        items.sort(key=lambda x: (x["type"] != "directory", x["name"].lower()))

        logger.info("Archive contents parsed for browsing",
                   archive=archive_name,
                   path=path,
                   items_count=len(items),
                   first_few_items=[item["name"] for item in items[:10]])

        return {"items": items}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to browse archive contents", repository_id=repository_id,
                    archive_name=archive_name, path=path, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to browse archive: {str(e)}"
        )
