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
from app.services.cache_service import archive_cache

logger = structlog.get_logger(__name__)

router = APIRouter()

@router.get("/{repository_id}/{archive_name}")
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
        all_items = await archive_cache.get(repository_id, archive_name)

        if all_items is not None:
            logger.info("Using cached archive contents",
                       archive=archive_name,
                       items_count=len(all_items))
        else:
            # If not in cache, fetch from borg
            result = await borg.list_archive_contents(
                repository.path,
                archive_name,
                path="",  # Always fetch all items
                remote_path=repository.remote_path,
                passphrase=repository.passphrase
            )

            # Parse all items
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
                                    "size": item_data.get("size"),
                                    "mtime": item_data.get("mtime")  # Modification time
                                })
                        except json.JSONDecodeError:
                            continue

                # Store in cache
                await archive_cache.set(repository_id, archive_name, all_items)
                logger.info("Cached archive contents",
                           archive=archive_name,
                           items_count=len(all_items))

        # Helper function to calculate directory size
        def calculate_directory_size(dir_path: str) -> int:
            """Calculate total size of all files in a directory recursively"""
            total_size = 0
            file_count = 0
            # Ensure consistent path format for comparison
            search_prefix = f"{dir_path}/" if dir_path else ""

            for item in all_items:
                item_path = item["path"]
                # Check if this item is under the directory
                if search_prefix:
                    if item_path.startswith(search_prefix) or item_path == dir_path:
                        # Only count files, not directories themselves
                        if item.get("type") != "d" and item.get("size") is not None:
                            total_size += item.get("size", 0)
                            file_count += 1
                else:
                    # Root level - count all files
                    if item.get("type") != "d" and item.get("size") is not None:
                        total_size += item.get("size", 0)
                        file_count += 1

            logger.debug("Directory size calculated",
                        dir_path=dir_path,
                        total_size=total_size,
                        file_count=file_count,
                        search_prefix=search_prefix)
            return total_size

        # Now filter the cached items for the requested path
        items = []
        seen_paths = set()

        for item in all_items:
            item_path = item["path"]
            item_type = item["type"]
            item_size = item.get("size")
            item_mtime = item.get("mtime")

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
                    full_dir_path = f"{path}/{dir_name}" if path else dir_name
                    # Calculate directory size
                    dir_size = calculate_directory_size(full_dir_path)
                    items.append({
                        "name": dir_name,
                        "type": "directory",
                        "size": dir_size,
                        "path": full_dir_path
                    })
            else:
                # This is an immediate child
                if relative_path not in seen_paths:
                    seen_paths.add(relative_path)
                    full_path = f"{path}/{relative_path}" if path else relative_path

                    # For directories, calculate their size
                    if item_type == "d":
                        dir_size = calculate_directory_size(full_path)
                        items.append({
                            "name": relative_path,
                            "type": "directory",
                            "size": dir_size,
                            "mtime": item_mtime,
                            "path": full_path
                        })
                    else:
                        # For files, use the actual size
                        items.append({
                            "name": relative_path,
                            "type": "file",
                            "size": item_size,
                            "mtime": item_mtime,
                            "path": full_path
                        })

        # Sort: directories first, then by name
        items.sort(key=lambda x: (x["type"] != "directory", x["name"].lower()))

        logger.info("Archive contents parsed for browsing",
                   archive=archive_name,
                   path=path,
                   items_count=len(items),
                   first_few_items=[item["name"] for item in items[:10]],
                   directory_sizes=[(item["name"], item.get("size")) for item in items[:5] if item["type"] == "directory"])

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
